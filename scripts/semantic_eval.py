#!/usr/bin/env python3
"""LLM を用いた盲検セマンティック検証のパック生成・検証・集計・FAQ 生成。

候補 LLM と採点 LLM はこのプログラムから直接呼ばない。候補へ渡す solver
bundle と、回答確定後に採点者へ渡す judge bundle を分離して生成する。
正解を見せない保証はプロンプトではなく、bundle の内容と実行時のアクセス制御で行う。

ケースは 1 ファイルに集約する（`ask`＝候補に見せる／`key`＝見せない）。分類は 1 語の
`expect`、採点対象は `key.must[].point` のみ。漏洩対策はアクセス制御と候補環境の隔離で行う。
`gen-faq` は同じケースから読者向け FAQ.md を生成する（`key` を出すので候補には渡さない）。
ケースと `must` の `faq`（省略時 true）が FAQ への掲載だけを制御し、採点対象は変えない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import secrets
import shutil
import sys
from pathlib import Path


PROTOCOL_VERSION = 2
CLASSIFICATIONS = {"determinate", "underdetermined", "inconsistent"}
# FAQ の読者向け分類ラベル
CLASSIFICATION_LABELS = {
    "determinate": "一意",
    "underdetermined": "未確定（空白）",
    "inconsistent": "矛盾",
}


class SemanticEvalError(ValueError):
    """入力・パック・LLM 出力がプロトコルに違反した。"""


def _read_json(path: Path):
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticEvalError(f"JSON を読めません: {path}: {exc}") from exc


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def _canonical_bytes(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest_json(value) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticEvalError(message)


def _fresh_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise SemanticEvalError(f"出力先が空ではありません: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _safe_source(repo_root: Path, rel: str) -> Path:
    _require(isinstance(rel, str) and rel, "source path は空でない文字列が必要です")
    _require(not Path(rel).is_absolute(), f"source path は相対パスで指定してください: {rel}")
    # '..' を含むと、解決後は repo 内でも bundle へのコピー先が out_dir を脱出しうる。
    _require(".." not in Path(rel).parts, f"source path に '..' は使えません: {rel}")
    full = (repo_root / rel).resolve()
    _require(_inside(full, repo_root), f"source path がリポジトリ外です: {rel}")
    _require(full.is_file(), f"source が存在しません: {rel}")
    return full


def _must_id(index: int) -> str:
    return f"must-{index}"


# `must.from` の項目参照（`I6#状態指定` → axioms.md の `<a id="i6-状態指定">`）。
# 公理（E/I）だけが項目アンカーを持つため、項目参照はこの形に限る。定理・応用ファイルは
# 群レベル（`T5`）・ファイル名（`magic.md`）のまま書く。
ITEM_REF = re.compile(r"^([EI]\d+)#(.+)$")
AXIOMS_REL = "world/core/axioms.md"


def item_anchor(ref: str) -> str | None:
    """`I6#状態指定` を axioms.md のアンカー名 `i6-状態指定` へ変換する。項目参照でなければ None。"""
    m = ITEM_REF.match(ref)
    return f"{m.group(1).lower()}-{m.group(2)}" if m else None


def axiom_anchors(repo_root: Path) -> set[str]:
    """axioms.md が定義する項目アンカーの集合。"""
    text = (repo_root / AXIOMS_REL).read_text(encoding="utf-8")
    return set(re.findall(r'<a id="([^"]+)"', text))


# 候補・採点者への指示テンプレート。judge.md は採点の判定規則を含むため、
# 書き換えると同じケース・同じ正典でも結果が変わる。実行条件として固定する。
TEMPLATE_NAMES = ("solver.md", "judge.md")


def template_hashes(repo_root: Path) -> dict:
    base = repo_root / "semantic-tests" / "templates"
    return {name: _digest_file(base / name) for name in TEMPLATE_NAMES}


def _in_faq(item) -> bool:
    """FAQ.md へ出すか。`faq` の省略時は出す。

    採点だけに要る基準（候補の振る舞いへの要求など）や、読者の疑問ではない検査用のケースを
    FAQ から外すために使う。採点対象はこのフラグに影響されない。
    """
    return item.get("faq", True)


def load_suite(suite_dir: Path, repo_root: Path):
    config = _read_json(suite_dir / "suite.json")
    _require(isinstance(config, dict), "suite.json はオブジェクトである必要があります")
    _require(config.get("protocol_version") == PROTOCOL_VERSION, "suite protocol_version が不正です")
    _require(isinstance(config.get("suite_id"), str), "suite_id が必要です")
    sources = config.get("source_paths")
    _require(isinstance(sources, list) and sources, "source_paths が必要です")
    for rel in sources:
        # 正典に検証用ファイル（key を含むケースや答えを出す FAQ）を混ぜると候補へ漏れる。
        norm = rel.replace("\\", "/") if isinstance(rel, str) else rel
        _require(
            not (isinstance(norm, str) and (norm.startswith("semantic-tests/") or norm == "FAQ.md")),
            f"source に検証用ファイル（semantic-tests/ や FAQ.md）は指定できません: {rel}",
        )
        _safe_source(repo_root, rel)

    cases = {}
    for path in sorted((suite_dir / "cases").glob("*.json")):
        case = _read_json(path)
        _require(isinstance(case, dict), f"case はオブジェクトである必要があります: {path}")
        case_id = case.get("id")
        _require(isinstance(case_id, str) and case_id, f"case id が不正です: {path}")
        _require(case_id not in cases, f"case id が重複しています: {case_id}")
        _validate_case(case, axiom_anchors(repo_root))
        cases[case_id] = case
    _require(bool(cases), "cases/*.json がありません")
    return config, cases


def _validate_case(case, anchors: set[str] | None = None) -> None:
    case_id = case["id"]
    _require(isinstance(case.get("title"), str) and case["title"], f"title が必要です: {case_id}")
    _require(isinstance(case.get("faq", True), bool), f"faq は真偽値です: {case_id}")
    ask = case.get("ask")
    _require(isinstance(ask, dict), f"ask が必要です: {case_id}")
    facts = ask.get("facts")
    _require(isinstance(facts, list) and facts, f"ask.facts が必要です: {case_id}")
    _require(all(isinstance(x, str) and x for x in facts), f"ask.facts は文字列配列です: {case_id}")
    _require(isinstance(ask.get("question"), str) and ask["question"], f"ask.question が必要です: {case_id}")

    key = case.get("key")
    _require(isinstance(key, dict), f"key が必要です: {case_id}")
    _require(key.get("expect") in CLASSIFICATIONS, f"key.expect が不正です: {case_id}")
    _require(isinstance(key.get("answer"), str) and key["answer"], f"key.answer が必要です: {case_id}")
    must = key.get("must")
    _require(isinstance(must, list) and must, f"key.must が必要です: {case_id}")
    for item in must:
        _require(isinstance(item, dict), f"key.must の要素は object です: {case_id}")
        _require(isinstance(item.get("point"), str) and item["point"], f"must.point が必要です: {case_id}")
        origin = item.get("from", [])
        _require(isinstance(origin, list), f"must.from は配列です: {case_id}")
        _require(all(isinstance(x, str) and x for x in origin), f"must.from は文字列配列です: {case_id}")
        # 項目参照は実在するアンカーを指すこと（本文からアンカーが消えたときの追随漏れを止める）
        for ref in origin:
            anchor = item_anchor(ref)
            if anchor is not None and anchors is not None:
                _require(
                    anchor in anchors,
                    f"must.from の項目参照が {AXIOMS_REL} に存在しません: {case_id}: {ref}",
                )
        _require(isinstance(item.get("faq", True), bool), f"must.faq は真偽値です: {case_id}")
    # 要点が一つも出ない FAQ の項目を作らない（ケースごと外すなら case.faq を false にする）
    _require(
        not _in_faq(case) or any(_in_faq(item) for item in must),
        f"FAQ に載せるケースには、FAQ に出す must が 1 つ以上必要です: {case_id}",
    )
    # ask に答えや根拠を書かない（候補へ漏れる）
    _require("must" not in ask and "answer" not in ask and "expect" not in ask,
             f"ask に key の項目を含めないでください: {case_id}")


def _solver_case(case, opaque: str) -> dict:
    """候補へ見せてよい部分だけを取り出す（key も title も含めない）。

    title は ask の外にあり、答えを書けてしまうため候補には渡さない（allowlist）。
    """
    return {
        "case_id": opaque,
        "facts": list(case["ask"]["facts"]),
        "question": case["ask"]["question"],
    }


def prepare_solver(
    suite_dir: Path,
    repo_root: Path,
    out_dir: Path,
    control_path: Path,
    seed: str | None = None,
    deny_read: list[str] | None = None,
) -> dict:
    _require(not _inside(control_path, out_dir), "control manifest を solver bundle 内に置けません")
    config, cases = load_suite(suite_dir, repo_root)
    _fresh_dir(out_dir)

    entropy = seed if seed is not None else secrets.token_hex(32)
    salt = hashlib.sha256(f"{config['suite_id']}\0{entropy}".encode()).hexdigest()
    rng = random.Random(int(salt, 16))
    case_ids = list(cases)
    rng.shuffle(case_ids)
    mapping = {}
    for case_id in case_ids:
        opaque = "case-" + hashlib.sha256(f"{salt}\0{case_id}".encode()).hexdigest()[:16]
        mapping[opaque] = case_id

    source_hashes = {}
    for rel in config["source_paths"]:
        src = _safe_source(repo_root, rel)
        dest = out_dir / "sources" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        source_hashes[rel] = _digest_file(src)

    for opaque, original in mapping.items():
        _write_json(out_dir / "cases" / f"{opaque}.json", _solver_case(cases[original], opaque))

    run_id = "run-" + hashlib.sha256(f"run\0{salt}".encode()).hexdigest()[:20]
    template = repo_root / "semantic-tests" / "templates" / "solver.md"
    task = template.read_text(encoding="utf-8").replace("{{RUN_ID}}", run_id)
    (out_dir / "TASK.md").write_text(task, encoding="utf-8")
    schema = repo_root / "semantic-tests" / "schemas" / "candidate-answer.schema.json"
    shutil.copyfile(schema, out_dir / "candidate-answer.schema.json")
    if deny_read:
        denied = [str(Path(path).expanduser().resolve()) for path in deny_read]
        candidate_settings = {
            "sandbox": {
                "enabled": True,
                "failIfUnavailable": True,
                "allowUnsandboxedCommands": False,
                "filesystem": {"denyRead": denied},
                "network": {"allowedDomains": []},
            },
            "permissions": {
                "deny": [*(f"Read({path}/**)" for path in denied), "WebFetch", "WebSearch"]
            },
        }
        _write_json(out_dir / "candidate-settings.json", candidate_settings)

    control = {
        "protocol_version": PROTOCOL_VERSION,
        "suite_id": config["suite_id"],
        "suite_dir": str(suite_dir.resolve()),
        "run_id": run_id,
        "case_mapping": mapping,
        "suite_config_sha256": _digest_json(config),
        "case_hashes": {case_id: _digest_json(case) for case_id, case in cases.items()},
        "source_hashes": source_hashes,
        "template_hashes": template_hashes(repo_root),
        "solver_bundle": str(out_dir.resolve()),
    }
    _write_json(control_path, control)
    return control


def validate_answer(
    suite_dir: Path,
    control_path: Path,
    answer_path: Path,
    sealed_path: Path,
    repo_root: Path,
) -> dict:
    control = _read_json(control_path)
    answer = _read_json(answer_path)
    _require(isinstance(control, dict), "control はオブジェクトである必要があります")
    _require(isinstance(answer, dict), "answer はオブジェクトである必要があります")
    _require(answer.get("protocol_version") == PROTOCOL_VERSION, "answer protocol_version が不正です")
    _require(answer.get("run_id") == control.get("run_id"), "answer run_id が一致しません")
    rows = answer.get("answers")
    _require(isinstance(rows, list), "answers は配列である必要があります")
    expected = set(control["case_mapping"])
    actual = set()
    for row in rows:
        _require(isinstance(row, dict), "answers の要素はオブジェクトです")
        cid = row.get("case_id")
        _require(cid in expected, f"未知の case_id です: {cid}")
        _require(cid not in actual, f"case_id が重複しています: {cid}")
        actual.add(cid)
        _require(row.get("classification") in CLASSIFICATIONS, f"classification が不正です: {cid}")
        _require(isinstance(row.get("conclusion"), str) and row["conclusion"].strip(), f"conclusion が必要です: {cid}")
        for key in ("reasoning_summary", "assumptions", "unresolved"):
            _require(isinstance(row.get(key), list), f"{key} は配列です: {cid}")
            _require(all(isinstance(x, str) for x in row[key]), f"{key} は文字列配列です: {cid}")
        confidence = row.get("confidence")
        _require(isinstance(confidence, (int, float)) and 0 <= confidence <= 1, f"confidence が不正です: {cid}")
        citations = row.get("citations")
        _require(isinstance(citations, list), f"citations は配列です: {cid}")
        for citation in citations:
            _require(isinstance(citation, dict), f"citation はオブジェクトです: {cid}")
            _require(citation.get("source") in control["source_hashes"], f"許可外 source の引用です: {cid}")
            _require(isinstance(citation.get("locator"), str), f"citation locator が必要です: {cid}")
            _require(isinstance(citation.get("supports"), str), f"citation supports が必要です: {cid}")
    _require(actual == expected, "回答された case_id の集合が一致しません")

    config, cases = load_suite(suite_dir, repo_root)
    _verify_control_inputs(control, config, cases, repo_root)

    sealed = {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": control["run_id"],
        "answer_sha256": _digest_json(answer),
        "answer": answer,
    }
    _write_json(sealed_path, sealed)
    return sealed


def prepare_judge(
    suite_dir: Path,
    control_path: Path,
    sealed_path: Path,
    out_dir: Path,
    repo_root: Path,
) -> None:
    control = _read_json(control_path)
    sealed = _read_json(sealed_path)
    _require(sealed.get("answer_sha256") == _digest_json(sealed.get("answer")), "sealed answer の hash が一致しません")
    _fresh_dir(out_dir)
    config, cases = load_suite(suite_dir, repo_root)
    _verify_control_inputs(control, config, cases, repo_root)

    rubrics = []
    for opaque, original in control["case_mapping"].items():
        case = cases[original]
        # 採点者には criterion の id/description と case（ask）だけを渡す。
        # expect・answer・must.from はスクリプト側だけが持ち、採点判断へのアンカリングを避ける。
        rubrics.append({
            "case_id": opaque,
            "case": {
                "title": case["title"],
                "facts": list(case["ask"]["facts"]),
                "question": case["ask"]["question"],
            },
            "criteria": [
                {"id": _must_id(i), "description": item["point"]}
                for i, item in enumerate(case["key"]["must"])
            ],
        })
    _write_json(out_dir / "rubrics.json", {"rubrics": rubrics})
    _write_json(out_dir / "candidate-answer.json", sealed["answer"])

    for rel in config["source_paths"]:
        src = _safe_source(repo_root, rel)
        dest = out_dir / "sources" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    template = repo_root / "semantic-tests" / "templates" / "judge.md"
    task = template.read_text(encoding="utf-8")
    task = task.replace("{{RUN_ID}}", control["run_id"])
    task = task.replace("{{ANSWER_SHA256}}", sealed["answer_sha256"])
    (out_dir / "TASK.md").write_text(task, encoding="utf-8")
    schema = repo_root / "semantic-tests" / "schemas" / "judgment.schema.json"
    shutil.copyfile(schema, out_dir / "judgment.schema.json")


def score(
    suite_dir: Path,
    control_path: Path,
    sealed_path: Path,
    judgment_paths: list[Path],
    report_path: Path,
    repo_root: Path,
) -> dict:
    _require(bool(judgment_paths), "judgment が 1 件以上必要です")
    resolved = [str(Path(p).resolve()) for p in judgment_paths]
    _require(len(set(resolved)) == len(resolved), "judgment パスが重複しています（同一ファイルの複数指定は不可）")
    control = _read_json(control_path)
    sealed = _read_json(sealed_path)
    answer = sealed.get("answer")
    _require(sealed.get("answer_sha256") == _digest_json(answer), "sealed answer の hash が一致しません")
    config, cases = load_suite(suite_dir, repo_root)
    _verify_control_inputs(control, config, cases, repo_root)
    minimum_judges = config.get("minimum_judges", 3)
    _require(
        isinstance(minimum_judges, int) and minimum_judges > 0,
        "minimum_judges が不正です",
    )
    _require(len(judgment_paths) >= minimum_judges, f"judgment は最低 {minimum_judges} 件必要です")
    _require(len(judgment_paths) % 2 == 1, "judgment は多数決のため奇数件にしてください")
    answers = {row["case_id"]: row for row in answer["answers"]}

    judgments = [_read_json(path) for path in judgment_paths]
    for judgment in judgments:
        _validate_judgment(judgment, control, sealed, cases)

    case_reports = []
    for opaque, original in control["case_mapping"].items():
        case = cases[original]
        key = case["key"]
        row = answers[opaque]
        classification_ok = row["classification"] == key["expect"]

        criteria_report = []
        tie = False
        all_pass = True
        for index, item in enumerate(key["must"]):
            criterion_id = _must_id(index)
            votes = []
            evidence = []
            for judgment in judgments:
                case_j = next(x for x in judgment["judgments"] if x["case_id"] == opaque)
                result = next(x for x in case_j["criterion_results"] if x["criterion_id"] == criterion_id)
                votes.append(result["passed"])
                evidence.append(result["evidence"])
            passed_votes = sum(votes)
            failed_votes = len(votes) - passed_votes
            if passed_votes == failed_votes:
                passed = None
                tie = True
            else:
                passed = passed_votes > failed_votes
            if passed is not True:
                all_pass = False
            criteria_report.append({
                "criterion_id": criterion_id,
                "point": item["point"],
                "passed": passed,
                "votes": votes,
                "evidence": evidence,
            })

        if tie:
            verdict = "needs_review"
        elif not classification_ok or not all_pass:
            verdict = "fail"
        else:
            verdict = "pass"
        case_reports.append({
            "case_id": opaque,
            "expected": key["expect"],
            "classification": row["classification"],
            "classification_passed": classification_ok,
            "verdict": verdict,
            "criteria": criteria_report,
        })

    verdicts = {item["verdict"] for item in case_reports}
    overall = "fail" if "fail" in verdicts else ("needs_review" if "needs_review" in verdicts else "pass")
    report = {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": control["run_id"],
        "answer_sha256": sealed["answer_sha256"],
        "judge_count": len(judgments),
        "overall_verdict": overall,
        "cases": case_reports,
    }
    _write_json(report_path, report)
    return report


def _validate_judgment(judgment, control, sealed, cases) -> None:
    _require(judgment.get("protocol_version") == PROTOCOL_VERSION, "judgment protocol_version が不正です")
    _require(judgment.get("run_id") == control["run_id"], "judgment run_id が一致しません")
    _require(judgment.get("answer_sha256") == sealed["answer_sha256"], "judgment answer_sha256 が一致しません")
    rows = judgment.get("judgments")
    _require(isinstance(rows, list), "judgments は配列です")
    by_case = {}
    for row in rows:
        cid = row.get("case_id")
        _require(cid in control["case_mapping"], f"judgment の case_id が不正です: {cid}")
        _require(cid not in by_case, f"judgment の case_id が重複しています: {cid}")
        by_case[cid] = row
        original = control["case_mapping"][cid]
        expected = {_must_id(i) for i in range(len(cases[original]["key"]["must"]))}
        results = row.get("criterion_results")
        _require(isinstance(results, list), f"criterion_results は配列です: {cid}")
        actual = set()
        for result in results:
            criterion_id = result.get("criterion_id")
            _require(criterion_id in expected, f"未知の criterion_id です: {criterion_id}")
            _require(criterion_id not in actual, f"criterion_id が重複しています: {criterion_id}")
            actual.add(criterion_id)
            _require(isinstance(result.get("passed"), bool), f"passed は bool です: {criterion_id}")
            _require(isinstance(result.get("evidence"), str), f"evidence が必要です: {criterion_id}")
        _require(actual == expected, f"criterion_id の集合が一致しません: {cid}")
    _require(set(by_case) == set(control["case_mapping"]), "judgment の case_id 集合が一致しません")


def _verify_control_inputs(control, config, cases, repo_root: Path) -> None:
    """開始後の正典・ケース（ask/key 双方）の差し替えを拒否する。"""
    _require(control.get("suite_config_sha256") == _digest_json(config), "suite.json が開始後に変更されています")
    _require(
        control.get("case_hashes") == {case_id: _digest_json(case) for case_id, case in cases.items()},
        "case が開始後に変更されています",
    )
    current_sources = {
        rel: _digest_file(_safe_source(repo_root, rel)) for rel in config["source_paths"]
    }
    _require(control.get("source_hashes") == current_sources, "source が開始後に変更されています")
    # template_hashes を持たない旧 control は、この検査の対象外とする（後方互換）
    if "template_hashes" in control:
        _require(
            control["template_hashes"] == template_hashes(repo_root),
            "templates（solver.md / judge.md）が開始後に変更されています",
        )


def render_faq(config, cases) -> str:
    """ケースから読者向け FAQ.md の本文を生成する（決定的）。"""
    lines = [
        "<!-- 自動生成ファイル。直接編集しないこと。`make faq` で再生成する。"
        "ソース: semantic-tests/public/cases/ -->",
        "# FAQ — 具体状況への世界法則の帰結",
        "",
        "公理・定理を具体的な状況へ当てはめた帰結の一覧。分類は "
        "**一意**（determinate: 結論が一つに定まる）／"
        "**未確定（空白）**（underdetermined: 現行文書では定まらない）／"
        "**矛盾**（inconsistent: 両立しない要求）。",
        "",
    ]
    for case_id in sorted(cases):
        case = cases[case_id]
        if not _in_faq(case):
            continue
        key = case["key"]
        label = CLASSIFICATION_LABELS[key["expect"]]
        lines.append(f"## {case['title']}")
        lines.append("")
        lines.append("**状況**")
        lines.append("")
        for fact in case["ask"]["facts"]:
            lines.append(f"- {fact}")
        lines.append("")
        lines.append(f"**問い**: {case['ask']['question']}")
        lines.append("")
        lines.append(f"**答え（{label}）**: {key['answer']}")
        lines.append("")
        lines.append("**要点**")
        lines.append("")
        for item in key["must"]:
            if not _in_faq(item):
                continue
            origin = item.get("from") or []
            suffix = f" — 導出: {', '.join(origin)}" if origin else ""
            lines.append(f"- {item['point']}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def coverage_map(repo_root: Path, cases) -> list[tuple[str, list[str]]]:
    """axioms.md の項目アンカーごとに、それを `from` に持つケース ID を集める（宣言順）。"""
    text = (repo_root / AXIOMS_REL).read_text(encoding="utf-8")
    by_anchor: dict[str, list[str]] = {a: [] for a in re.findall(r'<a id="([^"]+)"', text)}
    for case_id in sorted(cases):
        for item in cases[case_id]["key"]["must"]:
            for ref in item.get("from", []):
                anchor = item_anchor(ref)
                if anchor in by_anchor and case_id not in by_anchor[anchor]:
                    by_anchor[anchor].append(case_id)
    return list(by_anchor.items())


def render_coverage(repo_root: Path, cases) -> str:
    """被覆マップを生成する（決定的）。差分で被覆の増減を追うための成果物。"""
    rows = coverage_map(repo_root, cases)
    covered = sum(1 for _, ids in rows if ids)
    lines = [
        "<!-- 自動生成ファイル。直接編集しないこと。`make coverage` で再生成する。"
        "ソース: world/core/axioms.md, semantic-tests/public/cases/ -->",
        "# 公理項目の検査被覆",
        "",
        f"`world/core/axioms.md` の項目 {len(rows)} 件のうち、意味検証ケースが根拠に挙げているものは "
        f"{covered} 件。全項目の被覆は目標ではない（ケース化に適さない定義・補足を含むため）。"
        "この表は、改訂で被覆が失われたことを差分で見つけるために置く。",
        "",
        "| 項目 | 検査しているケース |",
        "|---|---|",
    ]
    for anchor, ids in rows:
        lines.append(f"| `{anchor}` | {'・'.join(ids) if ids else '（なし）'} |")
    return "\n".join(lines) + "\n"


def gen_coverage(suite_dir: Path, repo_root: Path, out_path: Path) -> str:
    _config, cases = load_suite(suite_dir, repo_root)
    text = render_coverage(repo_root, cases)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text


def gen_faq(suite_dir: Path, repo_root: Path, out_path: Path) -> str:
    config, cases = load_suite(suite_dir, repo_root)
    text = render_faq(config, cases)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="盲検 LLM セマンティック検証")
    parser.add_argument("--root", default=None, help="リポジトリルート")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare-solver", help="候補 LLM 用 bundle を生成")
    p.add_argument("--suite", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--control", required=True)
    p.add_argument("--seed", default=None, help="公開校正用。非公開本番では指定しない")
    p.add_argument(
        "--candidate-deny-read", action="append", default=[], metavar="PATH",
        help="候補 Claude Code から読ませないパス。複数指定可",
    )

    p = sub.add_parser("seal-answer", help="候補回答を検証して封印")
    p.add_argument("--suite", required=True)
    p.add_argument("--control", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("prepare-judge", help="採点 LLM 用 bundle を生成")
    p.add_argument("--suite", required=True)
    p.add_argument("--control", required=True)
    p.add_argument("--sealed", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("score", help="1 件以上の採点結果を集計")
    p.add_argument("--suite", required=True)
    p.add_argument("--control", required=True)
    p.add_argument("--sealed", required=True)
    p.add_argument("--judgment", action="append", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("gen-faq", help="ケースから読者向け FAQ.md を生成")
    p.add_argument("--suite", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("gen-coverage", help="公理項目ごとの検査被覆マップを生成")
    p.add_argument("--suite", required=True)
    p.add_argument("--out", required=True)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    try:
        if args.command == "prepare-solver":
            if not args.candidate_deny_read:
                print(
                    "warning: --candidate-deny-read 未指定のため candidate-settings.json "
                    "（サンドボックス）を生成しません。候補実行環境で正典外へのアクセスを別途遮断してください。",
                    file=sys.stderr,
                )
            control = prepare_solver(
                Path(args.suite), repo_root, Path(args.out), Path(args.control),
                args.seed, args.candidate_deny_read,
            )
            print(f"solver bundle: {Path(args.out).resolve()}")
            print(f"control manifest: {Path(args.control).resolve()}")
            print(f"run_id: {control['run_id']}")
        elif args.command == "seal-answer":
            sealed = validate_answer(Path(args.suite), Path(args.control), Path(args.answer), Path(args.out), repo_root)
            print(f"sealed answer: {Path(args.out).resolve()}")
            print(f"sha256: {sealed['answer_sha256']}")
        elif args.command == "prepare-judge":
            prepare_judge(Path(args.suite), Path(args.control), Path(args.sealed), Path(args.out), repo_root)
            print(f"judge bundle: {Path(args.out).resolve()}")
        elif args.command == "score":
            report = score(
                Path(args.suite), Path(args.control), Path(args.sealed),
                [Path(x) for x in args.judgment], Path(args.out), repo_root,
            )
            print(f"overall: {report['overall_verdict']}")
            print(f"report: {Path(args.out).resolve()}")
        elif args.command == "gen-faq":
            gen_faq(Path(args.suite), repo_root, Path(args.out))
            print(f"faq: {Path(args.out).resolve()}")
        elif args.command == "gen-coverage":
            gen_coverage(Path(args.suite), repo_root, Path(args.out))
            print(f"coverage: {Path(args.out).resolve()}")
        return 0
    except SemanticEvalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
