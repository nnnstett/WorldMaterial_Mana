"""ID 一意性チェック。同一ファイル内で E/I/T/Q ID が重複しないこと。"""
from __future__ import annotations

from typing import List

from ..model import Document
from ..report import Finding, Severity


def check_ids(doc: Document) -> List[Finding]:
    findings: List[Finding] = []
    seen = {}
    for h in doc.headings:
        if not h.id_code:
            continue
        if h.id_code in seen:
            findings.append(Finding(
                "ids.duplicate", Severity.ERROR, doc.path, h.line,
                f"ID {h.id_code} が重複（最初の定義: {seen[h.id_code]} 行目）。"
                f"廃止 ID は再利用しない",
            ))
        else:
            seen[h.id_code] = h.line
    return findings
