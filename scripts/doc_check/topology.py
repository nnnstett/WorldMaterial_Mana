"""相互参照トポロジー。

全ドキュメントを 1 つのグラフとして扱う。
- ノード: 各ファイル、および各ファイル内の見出しアンカー
- エッジ: リンク（出所ファイル・行 → 解決先ファイル・アンカー）

リンクチェックはこのトポロジー上で「解決先ノードが存在するか」「ID が整合するか」を
判定する。`to_dict()` / `to_dot()` で外部出力もできる。
"""
from __future__ import annotations

import posixpath
from typing import Dict, List, Optional

from .model import Document, Heading


class Topology:
    def __init__(self, documents: List[Document], existing_files=None):
        self.documents: Dict[str, Document] = {d.path: d for d in documents}
        # パースしない実在ファイル（LICENSE.md, 画像等）。存在チェックにのみ使う
        self.existing_files = set(existing_files or [])
        # ファイル → アンカー集合
        self.anchors: Dict[str, set] = {}
        # ファイル → {アンカー: Heading}
        self._heading_by_anchor: Dict[str, Dict[str, Heading]] = {}
        for d in documents:
            self.anchors[d.path] = {h.anchor for h in d.headings} | set(d.html_anchors)
            self._heading_by_anchor[d.path] = {h.anchor: h for h in d.headings}

    def resolve(self, source_path: str, target_file: str) -> str:
        """リンク先ファイル文字列を、リポジトリルート相対パスへ正規化する。

        先頭 "/" はリポジトリルート相対として扱う（GitHub と同じ）。
        """
        if not target_file:
            return source_path
        if target_file.startswith("/"):
            return target_file.lstrip("/")
        base = posixpath.dirname(source_path)
        return posixpath.normpath(posixpath.join(base, target_file))

    def has_file(self, path: str) -> bool:
        return path in self.documents or path in self.existing_files

    def has_anchor(self, path: str, anchor: str) -> bool:
        return anchor in self.anchors.get(path, set())

    def heading_at(self, path: str, anchor: str) -> Optional[Heading]:
        return self._heading_by_anchor.get(path, {}).get(anchor)

    def to_dict(self) -> dict:
        nodes = []
        for path, doc in self.documents.items():
            nodes.append({
                "file": path,
                "anchors": sorted(self.anchors[path]),
            })
        edges = []
        for doc in self.documents.values():
            for link in doc.links:
                target_path = self.resolve(doc.path, link.target_file)
                edges.append({
                    "from": doc.path,
                    "line": link.line,
                    "to_file": target_path,
                    "to_anchor": link.target_anchor,
                    "text": link.text,
                })
        return {"nodes": nodes, "edges": edges}

    def to_dot(self) -> str:
        lines = ["digraph docs {"]
        seen = set()
        for doc in self.documents.values():
            for link in doc.links:
                target_path = self.resolve(doc.path, link.target_file)
                edge = (doc.path, target_path)
                if edge in seen:
                    continue
                seen.add(edge)
                lines.append(f'  "{doc.path}" -> "{target_path}";')
        lines.append("}")
        return "\n".join(lines)
