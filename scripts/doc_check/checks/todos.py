"""ToDo を本文に置かないチェック。

書きかけ・課題は GitHub Issue で管理する。本文に TODO マーカー
（- [ ], TODO:, FIXME:）や `## ToDo` 節を置かない。
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document
from ..report import Finding, Severity

_TODO_MARK = re.compile(r"(- \[ \]|TODO:|FIXME:)")


def check_todos(doc: Document) -> List[Finding]:
    findings: List[Finding] = []
    for h in doc.headings:
        if "todo" in h.text.lower():
            findings.append(Finding(
                "todos.in-body", Severity.WARNING, doc.path, h.line,
                "`## ToDo` 節は置かず、課題は GitHub Issue で管理すること",
            ))
    for idx, raw in enumerate(doc.lines):
        if doc.line_is_code[idx]:
            continue
        if not _TODO_MARK.search(raw):
            continue
        findings.append(Finding(
            "todos.in-body", Severity.WARNING, doc.path, idx + 1,
            "TODO/FIXME・チェックボックスは本文に置かず、課題は GitHub Issue で管理すること",
        ))
    return findings
