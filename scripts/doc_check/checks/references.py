"""参照形式チェック。

命題（E/I/T/Q）をコードのみで参照することを禁止する（architecture.md §4.4）。
正しいリンク・ショートカット参照・範囲表現・列挙は許容する。
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document, iter_prose, mask_links
from ..report import Finding, Severity

_BARE_BRACKET = re.compile(r"\[([EITQ]\d+)\]")
_BARE_CODE = re.compile(r"[EITQ]\d+")
# 範囲・列挙を示す連結子（前後いずれかにあれば許容）
_CONNECTORS = set("〜~-–—+,、")


def check_references(doc: Document) -> List[Finding]:
    findings: List[Finding] = []
    for line_no, text in iter_prose(doc):
        masked = mask_links(text, doc.ref_defs)

        # [T1] のような裸の括弧付き ID（リンクでもショートカット参照でもない）
        bracket_spans = []
        for m in _BARE_BRACKET.finditer(masked):
            findings.append(Finding(
                "references.bare-bracket", Severity.ERROR, doc.path, line_no,
                f"コードのみの参照 [{m.group(1)}]。セクション名を含むリンクで書くこと",
            ))
            bracket_spans.append((m.start(), m.end()))

        # 括弧付きを除去してから裸コードを探す
        chars = list(masked)
        for s, e in bracket_spans:
            for i in range(s, e):
                chars[i] = " "
        stripped = "".join(chars)

        for m in _BARE_CODE.finditer(stripped):
            if _in_range_context(stripped, m.start(), m.end()):
                continue
            findings.append(Finding(
                "references.bare-code", Severity.ERROR, doc.path, line_no,
                f"散文中のコードのみ参照「{m.group(0)}」。"
                f"セクション名を含むリンクで書くこと",
            ))
    return findings


def _neighbor(text: str, idx: int, step: int) -> str:
    """idx から step 方向へ、空白を 1 つだけ読み飛ばして隣接文字を返す。"""
    j = idx
    seen_space = False
    while 0 <= j < len(text):
        ch = text[j]
        if ch == " " and not seen_space:
            seen_space = True
            j += step
            continue
        return ch
    return ""


def _in_range_context(text: str, start: int, end: int) -> bool:
    before = _neighbor(text, start - 1, -1)
    after = _neighbor(text, end, +1)
    return before in _CONNECTORS or after in _CONNECTORS
