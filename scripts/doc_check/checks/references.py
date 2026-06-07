"""参照形式チェック。

命題（E/I/T/Q）をコードのみで参照することを禁止する（architecture.md §4.4）。
範囲・列挙の例外は設けない。範囲を書きたい場合も両端をリンクで書く（強制はしないが、
リンクとして書かれていればリンク整合チェックが自然に走る）。
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document, iter_prose, mask_links
from ..report import Finding, Severity

_BARE_BRACKET = re.compile(r"\[([EITQ]\d+)\]")
_BARE_CODE = re.compile(r"[EITQ]\d+")


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
            findings.append(Finding(
                "references.bare-code", Severity.ERROR, doc.path, line_no,
                f"散文中のコードのみ参照「{m.group(0)}」。"
                f"セクション名を含むリンクで書くこと",
            ))
    return findings
