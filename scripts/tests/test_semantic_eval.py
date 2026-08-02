"""盲検セマンティック検証パイプラインのテスト（単一ファイル形式）。

public/ にケースを追加してもこれらのテストは壊れない（ケース集合に依存せず、
分類・must はすべて suite のケースから導出する）。正系（全通過→pass）に加え、
スコアリングと不変条件のガード（分類ハードゲート・must 失敗・改竄検知・sha 不一致・
奇数票）を負系で固定する。FAQ.md がケースと同期しているかも検査する。
"""
import json
import tempfile
import unittest
from pathlib import Path

from semantic_eval import (
    CLASSIFICATIONS,
    SemanticEvalError,
    load_suite,
    prepare_judge,
    prepare_solver,
    render_faq,
    score,
    validate_answer,
)


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "semantic-tests" / "public"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def load_cases():
    _config, cases = load_suite(SUITE, ROOT)
    return cases


def build_case(case_id, **overrides):
    """最小の妥当なケース。faq フラグの検査で使う。"""
    case = {
        "id": case_id,
        "title": f"{case_id} の題",
        "ask": {"facts": [f"{case_id} の状況。"], "question": f"{case_id} の問いか？"},
        "key": {
            "expect": "determinate",
            "answer": f"{case_id} の答え。",
            "must": [{"point": f"{case_id} の要点。", "from": ["I6"]}],
        },
    }
    case.update(overrides)
    return case


def build_suite(tmp, cases):
    """一時ディレクトリに、渡したケースだけを持つスイートを作る。"""
    suite = Path(tmp) / "suite"
    (suite / "cases").mkdir(parents=True)
    write_json(suite / "suite.json", {
        "protocol_version": 2, "suite_id": "faq-flag",
        "source_paths": ["world/core/axioms.md"],
    })
    for case in cases:
        write_json(suite / "cases" / f"{case['id']}.json", case)
    return suite


def build_answer(control, cases, classification_of=None):
    """全ケースに妥当な回答を作る。classification_of(expect)->str で分類を差し替え可能。"""
    primary_source = sorted(control["source_hashes"])[0]
    rows = []
    for opaque, original in control["case_mapping"].items():
        expect = cases[original]["key"]["expect"]
        classification = classification_of(expect) if classification_of else expect
        rows.append({
            "case_id": opaque,
            "classification": classification,
            "conclusion": "校正ケースの結論。",
            "reasoning_summary": ["必要な規則を確認した。"],
            "citations": [{
                "source": primary_source,
                "locator": "該当箇所",
                "supports": "結論の根拠。",
            }],
            "assumptions": [],
            "unresolved": [],
            "confidence": 0.8,
        })
    return {"protocol_version": 2, "run_id": control["run_id"], "answers": rows}


def build_judgments(control, cases, answer_sha256, count=3, passed_of=None):
    """count 件の妥当な採点を作る。passed_of(opaque, criterion_id)->bool で可否を差し替え可能。"""
    rows = []
    for opaque, original in control["case_mapping"].items():
        must = cases[original]["key"]["must"]
        rows.append({
            "case_id": opaque,
            "criterion_results": [{
                "criterion_id": f"must-{i}",
                "passed": passed_of(opaque, f"must-{i}") if passed_of else True,
                "evidence": "明示あり。",
            } for i in range(len(must))],
        })
    return [{
        "protocol_version": 2,
        "run_id": control["run_id"],
        "answer_sha256": answer_sha256,
        "judgments": rows,
    } for _ in range(count)]


class TestSemanticEval(unittest.TestCase):
    def _seal(self, base, control_path, answer):
        answer_path = base / "answer.json"
        sealed_path = base / "private" / "sealed.json"
        write_json(answer_path, answer)
        return validate_answer(SUITE, control_path, answer_path, sealed_path, ROOT), sealed_path

    def _score(self, base, control_path, sealed_path, judgments):
        paths = []
        for number, judgment in enumerate(judgments):
            path = base / f"judgment-{number}.json"
            write_json(path, judgment)
            paths.append(path)
        return score(SUITE, control_path, sealed_path, paths, base / "report.json", ROOT)

    def test_full_blind_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            solver = base / "solver"
            control_path = base / "private" / "control.json"
            control = prepare_solver(
                SUITE, ROOT, solver, control_path, seed="test-seed",
                deny_read=[str(ROOT.parent)],
            )
            cases = load_cases()

            self.assertTrue((solver / "TASK.md").is_file())
            settings = json.loads(
                (solver / "candidate-settings.json").read_text(encoding="utf-8")
            )
            self.assertIn(str(ROOT.parent.resolve()), settings["sandbox"]["filesystem"]["denyRead"])
            self.assertTrue(settings["sandbox"]["failIfUnavailable"])

            # solver bundle に key（答え・要点・title）が漏れていないこと。
            solver_text = "\n".join(
                p.read_text(encoding="utf-8")
                for p in solver.rglob("*") if p.is_file()
            )
            for original in control["case_mapping"].values():
                self.assertNotIn(cases[original]["key"]["answer"], solver_text)
                self.assertNotIn(cases[original]["title"], solver_text)
                for item in cases[original]["key"]["must"]:
                    self.assertNotIn(item["point"], solver_text)

            answer = build_answer(control, cases)
            sealed, sealed_path = self._seal(base, control_path, answer)

            judge_dir = base / "judge"
            prepare_judge(SUITE, control_path, sealed_path, judge_dir, ROOT)
            self.assertTrue((judge_dir / "rubrics.json").is_file())
            self.assertEqual(
                json.loads((judge_dir / "candidate-answer.json").read_text(encoding="utf-8")),
                answer,
            )
            # rubric には criterion の id/description と case のみ。expect/answer/from を渡さない。
            rubrics = json.loads((judge_dir / "rubrics.json").read_text(encoding="utf-8"))["rubrics"]
            for rubric in rubrics:
                self.assertEqual(set(rubric), {"case_id", "case", "criteria"})
                self.assertEqual(set(rubric["case"]), {"title", "facts", "question"})
                for criterion in rubric["criteria"]:
                    self.assertEqual(set(criterion), {"id", "description"})

            report = self._score(base, control_path, sealed_path, build_judgments(
                control, cases, sealed["answer_sha256"]))
            self.assertEqual(report["overall_verdict"], "pass")

    def test_wrong_classification_fails_even_if_must_pass(self):
        """expect と違う分類は、must が全通過でもハードゲートで fail。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control_path = base / "private" / "control.json"
            control = prepare_solver(SUITE, ROOT, base / "solver", control_path, seed="wrong-class")
            cases = load_cases()

            def wrong(expect):
                return next(c for c in sorted(CLASSIFICATIONS) if c != expect)

            answer = build_answer(control, cases, classification_of=wrong)
            sealed, sealed_path = self._seal(base, control_path, answer)
            report = self._score(base, control_path, sealed_path, build_judgments(
                control, cases, sealed["answer_sha256"]))
            self.assertEqual(report["overall_verdict"], "fail")
            for case in report["cases"]:
                self.assertFalse(case["classification_passed"])
                self.assertEqual(case["verdict"], "fail")

    def test_failed_must_fails(self):
        """must を1つ多数決で落とすと、分類が正しくても fail。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control_path = base / "private" / "control.json"
            control = prepare_solver(SUITE, ROOT, base / "solver", control_path, seed="must")
            cases = load_cases()
            target_case = next(iter(control["case_mapping"]))

            answer = build_answer(control, cases)
            sealed, sealed_path = self._seal(base, control_path, answer)
            report = self._score(base, control_path, sealed_path, build_judgments(
                control, cases, sealed["answer_sha256"],
                passed_of=lambda opaque, cid: not (opaque == target_case and cid == "must-0"),
            ))
            self.assertEqual(report["overall_verdict"], "fail")

    def test_even_judgment_count_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control_path = base / "private" / "control.json"
            control = prepare_solver(SUITE, ROOT, base / "solver", control_path, seed="even")
            cases = load_cases()
            answer = build_answer(control, cases)
            sealed, sealed_path = self._seal(base, control_path, answer)
            with self.assertRaisesRegex(SemanticEvalError, "奇数"):
                self._score(base, control_path, sealed_path, build_judgments(
                    control, cases, sealed["answer_sha256"], count=4))

    def test_below_minimum_judges_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control_path = base / "private" / "control.json"
            control = prepare_solver(SUITE, ROOT, base / "solver", control_path, seed="minjudges")
            cases = load_cases()
            answer = build_answer(control, cases)
            sealed, sealed_path = self._seal(base, control_path, answer)
            with self.assertRaisesRegex(SemanticEvalError, "最低"):
                self._score(base, control_path, sealed_path, build_judgments(
                    control, cases, sealed["answer_sha256"], count=1))

    def test_judgment_sha_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control_path = base / "private" / "control.json"
            control = prepare_solver(SUITE, ROOT, base / "solver", control_path, seed="sha")
            cases = load_cases()
            answer = build_answer(control, cases)
            sealed, sealed_path = self._seal(base, control_path, answer)
            with self.assertRaisesRegex(SemanticEvalError, "answer_sha256"):
                self._score(base, control_path, sealed_path, build_judgments(
                    control, cases, "0" * 64))

    def test_tampered_control_case_hash_rejected(self):
        """開始後に case（ask/key）が差し替わったこと（control の hash 不一致）を封印時に拒否する。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control_path = base / "private" / "control.json"
            control = prepare_solver(SUITE, ROOT, base / "solver", control_path, seed="tamper")
            cases = load_cases()

            tampered = json.loads(control_path.read_text(encoding="utf-8"))
            any_case = next(iter(tampered["case_hashes"]))
            tampered["case_hashes"][any_case] = "0" * 64
            control_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")

            answer = build_answer(control, cases)
            answer_path = base / "answer.json"
            write_json(answer_path, answer)
            with self.assertRaisesRegex(SemanticEvalError, "変更"):
                validate_answer(SUITE, control_path, answer_path, base / "sealed.json", ROOT)

    def test_control_manifest_cannot_be_in_solver_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "solver"
            with self.assertRaisesRegex(SemanticEvalError, "solver bundle"):
                prepare_solver(SUITE, ROOT, out, out / "control.json", seed="bad")

    def test_duplicate_judgment_paths_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            control_path = base / "private" / "control.json"
            control = prepare_solver(SUITE, ROOT, base / "solver", control_path, seed="dup")
            cases = load_cases()
            answer = build_answer(control, cases)
            sealed, sealed_path = self._seal(base, control_path, answer)
            judgment = build_judgments(control, cases, sealed["answer_sha256"], count=1)[0]
            jpath = base / "j.json"
            write_json(jpath, judgment)
            with self.assertRaisesRegex(SemanticEvalError, "重複"):
                score(SUITE, control_path, sealed_path, [jpath, jpath, jpath],
                      base / "report.json", ROOT)

    def test_source_path_with_dotdot_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            suite = Path(tmp) / "suite"
            (suite / "cases").mkdir(parents=True)
            write_json(suite / "suite.json", {
                "protocol_version": 2, "suite_id": "t",
                "source_paths": ["../etc/passwd"],
            })
            with self.assertRaisesRegex(SemanticEvalError, "使えません"):
                load_suite(suite, ROOT)

    def test_source_path_into_semantic_tests_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            suite = Path(tmp) / "suite"
            (suite / "cases").mkdir(parents=True)
            write_json(suite / "suite.json", {
                "protocol_version": 2, "suite_id": "t",
                "source_paths": ["semantic-tests/public/cases/clean-zone.json"],
            })
            with self.assertRaisesRegex(SemanticEvalError, "検証用ファイル"):
                load_suite(suite, ROOT)

    def test_faq_false_case_is_excluded_from_faq_only(self):
        """case.faq=false は FAQ から落ちるだけで、検査対象からは外れない。"""
        with tempfile.TemporaryDirectory() as tmp:
            shown, hidden = build_case("shown"), build_case("hidden", faq=False)
            suite = build_suite(tmp, [shown, hidden])
            config, cases = load_suite(suite, ROOT)

            faq = render_faq(config, cases)
            self.assertIn(shown["title"], faq)
            self.assertNotIn(hidden["title"], faq)

            control = prepare_solver(
                suite, ROOT, Path(tmp) / "solver", Path(tmp) / "private" / "control.json",
                seed="faq-case",
            )
            self.assertEqual(set(control["case_mapping"].values()), {"shown", "hidden"})

    def test_faq_false_must_is_excluded_from_faq_but_still_scored(self):
        """must.faq=false は FAQ の要点から落ちるが、採点基準としては残る。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            case = build_case("mixed")
            case["key"]["must"] = [
                {"point": "読者向けの要点。", "from": ["I6"]},
                {"point": "採点だけに要る基準。", "from": [], "faq": False},
            ]
            suite = build_suite(tmp, [case])
            config, cases = load_suite(suite, ROOT)

            faq = render_faq(config, cases)
            self.assertIn("読者向けの要点。", faq)
            self.assertNotIn("採点だけに要る基準。", faq)

            control_path = base / "private" / "control.json"
            control = prepare_solver(suite, ROOT, base / "solver", control_path, seed="faq-must")
            answer_path, sealed_path = base / "answer.json", base / "private" / "sealed.json"
            write_json(answer_path, build_answer(control, cases))
            validate_answer(suite, control_path, answer_path, sealed_path, ROOT)
            prepare_judge(suite, control_path, sealed_path, base / "judge", ROOT)

            rubrics = json.loads(
                (base / "judge" / "rubrics.json").read_text(encoding="utf-8")
            )["rubrics"]
            descriptions = [c["description"] for c in rubrics[0]["criteria"]]
            self.assertEqual(descriptions, ["読者向けの要点。", "採点だけに要る基準。"])

    def test_faq_case_without_any_faq_must_rejected(self):
        """要点が一つも出ない FAQ 項目は作らせない。"""
        with tempfile.TemporaryDirectory() as tmp:
            case = build_case("empty")
            case["key"]["must"] = [{"point": "採点専用。", "from": [], "faq": False}]
            with self.assertRaisesRegex(SemanticEvalError, "FAQ に出す must"):
                load_suite(build_suite(tmp, [case]), ROOT)

    def test_non_boolean_faq_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(SemanticEvalError, "faq は真偽値"):
                load_suite(build_suite(tmp, [build_case("bad", faq="no")]), ROOT)

    def test_faq_in_sync_with_cases(self):
        """コミット済み FAQ.md がケースから再生成した内容と一致すること（ドリフト防止）。"""
        config, cases = load_suite(SUITE, ROOT)
        expected = render_faq(config, cases)
        committed = (ROOT / "FAQ.md").read_text(encoding="utf-8")
        self.assertEqual(
            committed, expected,
            "FAQ.md がケースと同期していません。`make faq` で再生成してください。",
        )


if __name__ == "__main__":
    unittest.main()
