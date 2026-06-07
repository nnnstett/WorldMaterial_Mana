"""glossary 整合性チェック（カバレッジ）。

core ファイル（axioms/theorems/open-questions）に定義された全 ID が
glossary.md に登場すること。タグ整合の厳密化は glossary.md の書式確定後に拡張する。
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document
from ..report import Finding, Severity


def check_glossary_coverage(core_docs: List[Document], glossary: Document) -> List[Finding]:
    text = "\n".join(glossary.lines)
    findings: List[Finding] = []
    for doc in core_docs:
        for h in doc.headings:
            if not h.id_code:
                continue
            if not re.search(rf"\b{re.escape(h.id_code)}\b", text):
                findings.append(Finding(
                    "glossary.missing", Severity.ERROR, glossary.path, 1,
                    f"{h.id_code}（{doc.path}）が glossary.md に未登録",
                ))
    return findings
