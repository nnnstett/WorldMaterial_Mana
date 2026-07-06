"""必須セクションチェック。

- 公理群（E/I）: 公理・関連（命題・詳細・導出元は置けない）
- 定理（T）: 命題・導出元・関連（「公理」リストは置けない）
- 行使形態の定義（`## 行使形態の定義` 節下の T）: 定義・定義対象・関連
  （命題・導出元・証明スケッチ・「公理」リストは置けない）
- 未解明領域（Q）: 背景・現在判明・空白の意図・関連
- 応用ファイル: 冒頭の「前提」行
"""
from __future__ import annotations

from typing import List

from ..model import Document
from ..report import Finding, Severity
from ..config import classify

# 定理ファイル内でこの H2 節に属する T エントリは「行使形態の定義」様式となる
DEFINITION_H2 = "行使形態の定義"

# 接頭辞 → (ラベル表示名, 本文中で探す部分文字列)
_REQUIRED = {
    "E": [("公理", "**公理**"), ("関連", "**関連**")],
    "I": [("公理", "**公理**"), ("関連", "**関連**")],
    "T": [("命題", "**命題**"), ("導出元", "**導出元**"), ("関連", "**関連**")],
    "T-definition": [("定義", "**定義**"), ("定義対象", "**定義対象**"), ("関連", "**関連**")],
    "Q": [
        ("背景", "**背景**"),
        ("現在判明していること", "判明"),
        ("この空白の意図", "空白の意図"),
        ("関連", "**関連**"),
    ],
}

# 種別に置いてはならないセクション（公理群と定理の構造非対称を機械的に担保する）
_FORBIDDEN = {
    "E": [("命題", "**命題**"), ("詳細", "**詳細**"), ("導出元", "**導出元**")],
    "I": [("命題", "**命題**"), ("詳細", "**詳細**"), ("導出元", "**導出元**")],
    "T": [("公理", "**公理**")],
    "T-definition": [
        ("公理", "**公理**"),
        ("命題", "**命題**"),
        ("導出元", "**導出元**"),
        ("証明スケッチ", "**証明スケッチ**"),
    ],
}


def h2_context(doc: Document, line: int) -> str:
    """指定行の直前にある H2 見出しのテキストを返す（無ければ空文字列）。"""
    ctx = ""
    for hh in doc.headings:
        if hh.line > line:
            break
        if hh.level == 2:
            ctx = hh.text
    return ctx


def _body_lines(doc: Document, index: int) -> List[str]:
    """headings[index] の本文（次の同レベル以上の見出しまで）を返す。"""
    h = doc.headings[index]
    start = h.line  # 1-based の見出し行
    end = len(doc.lines)
    for nxt in doc.headings[index + 1:]:
        if nxt.level <= h.level:
            end = nxt.line - 1
            break
    return doc.lines[start:end]


def check_sections(doc: Document) -> List[Finding]:
    findings: List[Finding] = []

    has_proposition = False
    for i, h in enumerate(doc.headings):
        if not h.id_code:
            continue
        prefix = h.id_code[0]
        if prefix == "T" and DEFINITION_H2 in h2_context(doc, h.line):
            prefix = "T-definition"
        required = _REQUIRED.get(prefix)
        if not required:
            continue
        has_proposition = True
        body = "\n".join(_body_lines(doc, i))
        for label, needle in required:
            if needle not in body:
                findings.append(Finding(
                    "sections.missing", Severity.ERROR, doc.path, h.line,
                    f"{h.id_code} に必須セクション「{label}」が無い",
                ))
        for label, needle in _FORBIDDEN.get(prefix, []):
            if needle in body:
                findings.append(Finding(
                    "sections.forbidden", Severity.ERROR, doc.path, h.line,
                    f"{h.id_code} に置けないセクション「{label}」がある",
                ))

    # 応用ファイル: 冒頭の前提行
    if not has_proposition and classify(doc.path) == "applied":
        head = "\n".join(doc.lines[:8])
        if "前提" not in head:
            findings.append(Finding(
                "sections.missing-premise", Severity.ERROR, doc.path, 1,
                "応用ファイル冒頭に「前提」リストが無い",
            ))
    return findings
