"""分量上限チェック（暴走防止）。

閾値は thresholds.json。原則 error。`<!-- check:length-exempt 理由 -->` を
直前に置くと、続く非空ブロックの分量 finding を抑制する。
"""
from __future__ import annotations

import re
from typing import List, Set

from ..model import Document, mask_inline_code, mask_links, _REF_DEF
from ..report import Finding, Severity
from ..config import Config, classify
from .sections import DEFINITION_H2, h2_context

_LIST_ITEM = re.compile(r"^\s*([-*+]|\d+\.)\s+\S")
_EXEMPT = "check:length-exempt"
_PROP = "**命題**"


def _exempt_lines(doc: Document) -> Set[int]:
    """例外コメント直後の非空ブロックの行番号集合（1-based）。"""
    suppressed: Set[int] = set()
    lines = doc.lines
    for i, raw in enumerate(lines):
        if _EXEMPT not in raw:
            continue
        suppressed.add(i + 1)
        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        while j < len(lines) and lines[j].strip() != "":
            suppressed.add(j + 1)
            j += 1
    return suppressed


def _entry_spans(doc: Document):
    """id を持つ見出しごとに (heading, start_line, end_line) を返す（1-based, 包含）。"""
    spans = []
    for idx, h in enumerate(doc.headings):
        if not h.id_code:
            continue
        end = len(doc.lines)
        for nxt in doc.headings[idx + 1:]:
            if nxt.level <= h.level:
                end = nxt.line - 1
                break
        spans.append((h, h.line, end))
    return spans


def check_volume(doc: Document, config: Config) -> List[Finding]:
    th = config.thresholds
    suppressed = _exempt_lines(doc)
    findings: List[Finding] = []

    def emit(rule, line, msg, severity=Severity.ERROR):
        if line in suppressed:
            return
        findings.append(Finding(rule, severity, doc.path, line, msg))

    # 見出し階層の深さ
    for h in doc.headings:
        if h.level > th["heading_max_depth"]:
            emit("volume.heading-depth", h.line,
                 f"見出しが深すぎる（H{h.level} > H{th['heading_max_depth']}）")

    # 箇条書きの数（連続するリスト項目のラン）
    run_start = None
    run_count = 0
    for idx, raw in enumerate(doc.lines):
        is_item = bool(_LIST_ITEM.match(raw)) and not doc.line_is_code[idx]
        if is_item:
            if run_start is None:
                run_start = idx + 1
            run_count += 1
        else:
            if run_start is not None and run_count > th["list_max_items"]:
                emit("volume.list-items", run_start,
                     f"リスト項目が多すぎる（{run_count} > {th['list_max_items']}）")
            run_start, run_count = None, 0
    if run_start is not None and run_count > th["list_max_items"]:
        emit("volume.list-items", run_start,
             f"リスト項目が多すぎる（{run_count} > {th['list_max_items']}）")

    # ファイル全体の行数（応用ファイル）
    if classify(doc.path) == "applied":
        n = len(doc.lines)
        if n > th["applied_file_max_lines"]:
            emit("volume.file-length", 1,
                 f"応用ファイルが長すぎる（{n} 行 > {th['applied_file_max_lines']}）")

    # 命題ごと（文数・エントリ文字数）
    for h, start, end in _entry_spans(doc):
        body = doc.lines[start:end]
        prefix = h.id_code[0] if h.id_code else ""
        # 行使形態の定義（H2 節キーで判別）は主部が **定義**
        main_label, label_name = _PROP, "命題"
        if prefix == "T" and DEFINITION_H2 in h2_context(doc, h.line):
            main_label, label_name = "**定義**", "定義"
        for offset, raw in enumerate(body):
            if main_label in raw:
                after = raw.split(main_label, 1)[1].lstrip("：: ")
                sentences = [s for s in after.split("。") if s.strip()]
                if len(sentences) > th["proposition_max_sentences"]:
                    emit("volume.proposition", start + offset,
                         f"{label_name}が {len(sentences)} 文（上限 {th['proposition_max_sentences']} 文）")
                break

        # 参照定義行（[label]: url）は本文ではないため字数に数えない
        # （最終エントリの範囲はファイル末尾まで伸び、参照定義ブロックを含むため）
        prose = [raw for raw in body if not _REF_DEF.match(raw)]
        text = mask_links(mask_inline_code("\n".join(prose)), doc.ref_defs)
        # 名前付きアンカー等の HTML タグは読者に見えないため字数に数えない
        text = re.sub(r"<[^>]+>", "", text)
        chars = len(re.sub(r"\s", "", text))
        if prefix in ("E", "I"):
            # 公理群の字数は命題分割ではなくグルーピング見直しのシグナル。
            # 警告水準を超えたら概念の切り出しを検討し、上限で強制する
            if chars > th["axiom_entry_max_chars"]:
                emit("volume.entry-length", h.line,
                     f"公理群が長すぎる（{chars} 字 > {th['axiom_entry_max_chars']}、リンク除く）。概念の切り出しを行う")
            elif chars > th["entry_max_chars"]:
                emit("volume.axiom-entry-heavy", h.line,
                     f"公理群が重い（{chars} 字 > {th['entry_max_chars']}、リンク除く）。グルーピング見直しのシグナル",
                     Severity.WARNING)
        elif chars > th["entry_max_chars"]:
            emit("volume.entry-length", h.line,
                 f"エントリが長すぎる（{chars} 字 > {th['entry_max_chars']}、リンク除く）")

    return findings
