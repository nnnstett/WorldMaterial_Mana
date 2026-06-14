"""禁止語チェック。

廃止した分類の用語・接頭辞が本文に現れないこと。
- 「補題」（数学用語）
- 「波長」（旧用語。真度・位相に分離して廃止）
- 旧接頭辞コード L#, C#（廃止した補題・系の ID）

注: 「系」単体は「体系」「系統」等の複合語と区別できず誤検出が多いため、
substring 走査の対象にしない（scripts/README.md 参照）。引用（>）・コード内は除外。
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document, iter_prose
from ..report import Finding, Severity

_TERMS = {
    "補題": "禁止語「補題」。4 分類（E/I/T/Q）では使用しない",
    "波長": "禁止語「波長」。真度（マナとの共鳴のしやすさ）と位相（個体間の適合）に分離して廃止",
}
_OLD_CODE = re.compile(r"(?<![A-Za-z\-])[LC]\d+(?![\-\dA-Za-z])")


def check_forbidden(doc: Document) -> List[Finding]:
    findings: List[Finding] = []
    for line_no, text in iter_prose(doc):
        if text.lstrip().startswith(">"):
            continue
        for term, message in _TERMS.items():
            if term in text:
                findings.append(Finding(
                    "forbidden.term", Severity.ERROR, doc.path, line_no,
                    message,
                ))
        for m in _OLD_CODE.finditer(text):
            findings.append(Finding(
                "forbidden.code", Severity.ERROR, doc.path, line_no,
                f"廃止接頭辞コード「{m.group(0)}」（補題 L / 系 C は廃止）",
            ))
    return findings
