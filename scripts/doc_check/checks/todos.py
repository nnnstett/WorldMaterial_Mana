"""TODO 散在チェック。

TODO マーカー（- [ ], TODO:, FIXME:）はファイル末尾の `## ToDo` 節以外に
現れないこと。
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document
from ..report import Finding, Severity

_TODO_MARK = re.compile(r"(- \[ \]|TODO:|FIXME:)")


def _todo_section_line(doc: Document) -> int:
    for h in doc.headings:
        if "todo" in h.text.lower():
            return h.line
    return -1


def check_todos(doc: Document) -> List[Finding]:
    findings: List[Finding] = []
    todo_line = _todo_section_line(doc)
    for idx, raw in enumerate(doc.lines):
        if doc.line_is_code[idx]:
            continue
        line_no = idx + 1
        if not _TODO_MARK.search(raw):
            continue
        if todo_line != -1 and line_no > todo_line:
            continue  # ToDo 節以降は許容
        findings.append(Finding(
            "todos.scattered", Severity.WARNING, doc.path, line_no,
            "TODO/FIXME は末尾の `## ToDo` 節にまとめること",
        ))
    return findings
