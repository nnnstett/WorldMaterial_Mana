"""リンクチェック（トポロジー上で実行）。

- missing-file: 参照先ファイルが存在しない
- missing-anchor: 参照先ファイルにアンカー（見出し）が存在しない
- id-mismatch: リンクテキストの ID コードと、参照先見出しの ID コードが食い違う
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


def _nearest_id_heading(doc: Document, line: int):
    """指定行より前で最も近い、ID コード付き見出しを返す。"""
    owner = None
    for h in doc.headings:
        if h.line >= line:
            break
        if h.id_code:
            owner = h
    return owner


def check_links(doc: Document, topo: Topology) -> List[Finding]:
    findings: List[Finding] = []

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
