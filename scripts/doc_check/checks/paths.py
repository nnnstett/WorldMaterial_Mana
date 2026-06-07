"""旧パス検出チェック。再構築前のファイル名・ディレクトリへの参照が残らないこと。"""
from __future__ import annotations

from typing import List

from ..model import Document, iter_prose
from ..report import Finding, Severity

_OLD_PATHS = [
    "世界の法則.md",
    "魔法.md",
    "魔術.md",
    "超能力.md",
    "種族.md",
    "/dungeon.md",
    "character/",
    "history/",
]


def check_paths(doc: Document) -> List[Finding]:
    findings: List[Finding] = []
    for line_no, text in iter_prose(doc):
        for old in _OLD_PATHS:
            if old in text:
                findings.append(Finding(
                    "paths.old-path", Severity.ERROR, doc.path, line_no,
                    f"旧パス「{old}」への参照。新パス（world/ 配下・英字名）に更新すること",
                ))
    return findings
