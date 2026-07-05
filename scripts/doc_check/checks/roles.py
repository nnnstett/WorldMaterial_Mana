"""役割セクションチェック。

- 公理群（E/I）: 公理 → 定義 → 観測事実 → 目安 → 補足 → 空白 → 関連 の固定順。
  規約外のセクション名は置けない
- 定理（T）: 命題 → 導出元 → 証明スケッチ → 詳細 → 観測事実 → 空白 → 関連
- 空白セクションの箇条は未解明領域（Q）へのリンクを必ず伴う

セクションは行頭の太字ラベル（`**名前**:` や `**名前**（…）:`）を指す。
箇条書き・番号リスト内の太字（見出し語）は対象外。
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document
from ..report import Finding, Severity

# 行頭の太字セクション名（（や : の手前まで）。リスト項目は先頭が - / 数字のため一致しない
_SECTION = re.compile(r"^\*\*([^*（(:]+)\*\*")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\S")

_ORDER = {
    "axiom": ["公理", "定義", "観測事実", "目安", "補足", "空白", "関連"],
    "theorem": ["命題", "導出元", "証明スケッチ", "詳細", "観測事実", "空白", "関連"],
}


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


def check_roles(doc: Document) -> List[Finding]:
    findings: List[Finding] = []

    for h, start, end in _entry_spans(doc):
        prefix = h.id_code[0]
        if prefix in ("E", "I"):
            order = _ORDER["axiom"]
        elif prefix == "T":
            order = _ORDER["theorem"]
        else:
            continue

        prev_idx = -1
        in_blank = False
        for i in range(start, end):
            raw = doc.lines[i]
            if doc.line_is_code[i]:
                continue
            m = _SECTION.match(raw)
            if m:
                name = m.group(1)
                in_blank = (name == "空白")
                if name not in order:
                    findings.append(Finding(
                        "roles.unknown-section", Severity.ERROR, doc.path, i + 1,
                        f"{h.id_code} に規約外のセクション「{name}」がある",
                    ))
                    continue
                idx = order.index(name)
                if idx < prev_idx:
                    findings.append(Finding(
                        "roles.section-order", Severity.ERROR, doc.path, i + 1,
                        f"{h.id_code} のセクション「{name}」の順序が規約（{' → '.join(order)}）に反する",
                    ))
                prev_idx = max(prev_idx, idx)
                continue
            if in_blank and _LIST_ITEM.match(raw):
                if "[Q" not in raw and "open-questions.md" not in raw:
                    findings.append(Finding(
                        "roles.blank-missing-q", Severity.ERROR, doc.path, i + 1,
                        f"{h.id_code} の空白セクションの箇条に Q へのリンクが無い",
                    ))
    return findings
