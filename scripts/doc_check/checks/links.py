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


def check_links(doc: Document, topo: Topology) -> List[Finding]:
    findings: List[Finding] = []
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
    return findings
