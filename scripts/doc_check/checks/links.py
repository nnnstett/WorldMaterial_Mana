"""リンクチェック（トポロジー上で実行）。

- missing-file: 参照先ファイルが存在しない
- missing-anchor: 参照先ファイルにアンカー（見出し）が存在しない
- id-mismatch: リンクテキストの ID コードと、参照先見出し／項目アンカーの ID が食い違う
- duplicate-anchor: 名前付きアンカーの重複・見出しアンカーとの衝突
- anchor-format / anchor-owner-mismatch: 項目アンカーの命名規則・所属群一致
- anchor-placement: 項目アンカーが公理項目（番号付きリスト）の行末にあるか
- item-anchor-scope: 項目アンカーへの参照が world/ 配下に限られているか
  （world/ 内での使い分け——依存の引用か純粋なポインタか——はレビューで判断する）
- item-anchor-derivation (warning): 証明スケッチが項目アンカーで引用する公理群が、
  その定理の導出元に列挙されているか（群単位リンクは数えない近似。隠れた前提の示唆。
  §4.1 の「用語の定義参照は前提使用に数えない」例外は機械では判別できないため、
  warning は人手確認前提）

各チェックが保証する規約条項は docs/architecture.md §5.5 保証マップを参照。
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document
from ..topology import Topology
from ..report import Finding, Severity

_LEADING_ID = re.compile(r"^([EITQ]\d+)")
# 項目アンカー（HTML アンカー）の ID 接頭辞（例: "e5-大きさ" → "e5"）
_ANCHOR_ID = re.compile(r"^([eitq]\d+)-")
# 行頭の太字セクションラベル（例: **証明スケッチ**:）。リスト項目内の太字は一致しない
_SECTION_LABEL = re.compile(r"^\*\*([^*（(:]+)\*\*")
# 番号付きリスト項目（公理項目）
_NUMBERED_ITEM = re.compile(r"^\s*\d+\.\s+\S")
_PROOF_SECTION = "証明スケッチ"
_DERIVATION_SECTION = "導出元"


def _nearest_id_heading(doc: Document, line: int):
    """指定行より前で最も近い、ID コード付き見出しを返す。"""
    owner = None
    for h in doc.headings:
        if h.line >= line:
            break
        if h.id_code:
            owner = h
    return owner


def _derivation_ids_by_entry(doc: Document, section_labels) -> dict:
    """エントリ見出し行 → 導出元セクションに列挙された ID 集合。"""
    ids: dict = {}
    for link in doc.links:
        if section_labels.get(link.line) != _DERIVATION_SECTION:
            continue
        m = _LEADING_ID.match(link.text)
        if not m:
            continue
        entry = _nearest_id_heading(doc, link.line)
        if entry is None:
            continue
        ids.setdefault(entry.line, set()).add(m.group(1))
    return ids


def _section_labels_by_line(doc: Document):
    """各行が属する行頭太字セクション名を 行番号 → 名前 で返す（見出しでリセット）。"""
    heading_lines = {h.line for h in doc.headings}
    labels = {}
    current = None
    for idx, raw in enumerate(doc.lines):
        line_no = idx + 1
        if line_no in heading_lines:
            current = None
        elif not doc.line_is_code[idx]:
            m = _SECTION_LABEL.match(raw)
            if m:
                current = m.group(1)
        labels[line_no] = current
    return labels


def check_links(doc: Document, topo: Topology) -> List[Finding]:
    findings: List[Finding] = []
    section_labels = None  # 項目アンカー参照の検査時に遅延構築
    derivation_ids = None  # 導出元包含の検査時に遅延構築

    # 名前付きアンカー自体の検査（一意性・見出し衝突・命名規則・所属群）
    seen = {}
    heading_anchors = {h.anchor for h in doc.headings}
    for name, line in doc.html_anchor_occurrences:
        if name in seen:
            findings.append(Finding(
                "links.duplicate-anchor", Severity.ERROR, doc.path, line,
                f"名前付きアンカーが重複している: {name}（初出: {seen[name]} 行）",
            ))
        else:
            seen[name] = line
        if name in heading_anchors:
            findings.append(Finding(
                "links.duplicate-anchor", Severity.ERROR, doc.path, line,
                f"名前付きアンカーが見出しアンカーと衝突している: {name}",
            ))
        am = _ANCHOR_ID.match(name)
        if am:
            owner = _nearest_id_heading(doc, line)
            if owner and owner.id_code and owner.id_code.lower() != am.group(1):
                findings.append(Finding(
                    "links.anchor-owner-mismatch", Severity.ERROR, doc.path, line,
                    f"項目アンカー（{name}）の ID 接頭辞と、所属する見出し"
                    f"（[{owner.id_code}]）が不一致",
                ))
            if doc.path.startswith("world/core/"):
                raw = doc.lines[line - 1]
                at_line_end = re.search(
                    r'<a\s+id="' + re.escape(name) + r'"\s*>\s*</a>\s*$', raw)
                if not (_NUMBERED_ITEM.match(raw) and at_line_end):
                    findings.append(Finding(
                        "links.anchor-placement", Severity.ERROR, doc.path, line,
                        f"項目アンカー（{name}）は公理項目（番号付きリスト）の行末に置く",
                    ))
        elif doc.path.startswith("world/core/"):
            findings.append(Finding(
                "links.anchor-format", Severity.ERROR, doc.path, line,
                f"項目アンカー名が命名規則（小文字ID-スラッグ）に従っていない: {name}",
            ))

    for link in doc.links:
        # 外部リンク（スキーム付き・mailto 等）は対象外
        if "://" in link.target_file or link.target_file.startswith("mailto:"):
            continue
        target_path = topo.resolve(doc.path, link.target_file)

        if not topo.has_file(target_path):
            findings.append(Finding(
                "links.missing-file", Severity.ERROR, doc.path, link.line,
                f"参照先ファイルが存在しない: {target_path}（リンク: [{link.text}]）",
            ))
            continue

        # アンカー検証はパース済みドキュメントに対してのみ可能
        if (
            link.target_anchor
            and target_path in topo.documents
            and not topo.has_anchor(target_path, link.target_anchor)
        ):
            findings.append(Finding(
                "links.missing-anchor", Severity.ERROR, doc.path, link.line,
                f"参照先にアンカーが無い: {target_path}#{link.target_anchor}",
            ))
            continue

        # 項目アンカー参照の適用範囲（world/ 配下でのみ使える。world/ 内での
        # 使い分け——項目への依存の引用か純粋なポインタか——はレビューで判断する）
        if (
            link.target_anchor
            and target_path in topo.documents
            and _ANCHOR_ID.match(link.target_anchor)
            and topo.heading_at(target_path, link.target_anchor) is None
            and topo.has_anchor(target_path, link.target_anchor)
        ):
            if not doc.path.startswith("world/"):
                findings.append(Finding(
                    "links.item-anchor-scope", Severity.ERROR, doc.path, link.line,
                    f"項目アンカー参照（{target_path}#{link.target_anchor}）は"
                    f"world/ 配下でのみ使う。ほかのファイルでは群単位リンクで書く",
                ))
            else:
                if section_labels is None:
                    section_labels = _section_labels_by_line(doc)
                entry = _nearest_id_heading(doc, link.line)
                in_theorem_proof = (
                    section_labels.get(link.line) == _PROOF_SECTION
                    and entry is not None
                    and entry.id_code.startswith("T")
                )
                if in_theorem_proof:
                    # 引用した公理群が導出元に列挙されているか（隠れた前提の近似検出）
                    if derivation_ids is None:
                        derivation_ids = _derivation_ids_by_entry(doc, section_labels)
                    group = _ANCHOR_ID.match(link.target_anchor).group(1).upper()
                    if group not in derivation_ids.get(entry.line, set()):
                        findings.append(Finding(
                            "links.item-anchor-derivation", Severity.WARNING,
                            doc.path, link.line,
                            f"証明スケッチが {group} の項目（#{link.target_anchor}）を"
                            f"引用しているが、導出元に {group} が列挙されていない"
                            f"（前提として使っているなら導出元へ追加、用語の指し先なら"
                            f"群単位リンクへ変更 → architecture.md §4.1）",
                        ))

        # ID 整合（リンクテキスト先頭の ID と参照先見出しの ID）
        m = _LEADING_ID.match(link.text)
        if m and link.target_anchor:
            heading = topo.heading_at(target_path, link.target_anchor)
            # 見出しが ID を持つ場合のみ照合（重要な帰結節など ID 無し見出しはスキップ）
            if heading and heading.id_code and heading.id_code != m.group(1):
                findings.append(Finding(
                    "links.id-mismatch", Severity.ERROR, doc.path, link.line,
                    f"リンクテキストの ID（{m.group(1)}）と参照先見出しの ID"
                    f"（{heading.id_code}）が不一致",
                ))
            elif heading is None:
                # 項目アンカー（名前付きアンカー）: アンカー名の ID 接頭辞と照合
                am = _ANCHOR_ID.match(link.target_anchor)
                if am and am.group(1).upper() != m.group(1):
                    findings.append(Finding(
                        "links.id-mismatch", Severity.ERROR, doc.path, link.line,
                        f"リンクテキストの ID（{m.group(1)}）と項目アンカーの ID"
                        f"（{am.group(1).upper()}）が不一致",
                    ))
    return findings
