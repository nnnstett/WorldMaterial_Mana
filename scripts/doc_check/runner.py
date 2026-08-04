"""チェックの実行オーケストレーション。

全ドキュメントをパース→トポロジー構築→ファイルごとにスコープ別チェックを実行。
"""
from __future__ import annotations

import os
from typing import List

from .model import parse_document, Document
from .topology import Topology
from .config import Config, classify
from .report import Finding
from .checks.links import check_links
from .checks.references import check_references
from .checks.ids import check_ids
from .checks.sections import check_sections
from .checks.roles import check_roles
from .checks.forbidden import check_forbidden
from .checks.paths import check_paths
from .checks.volume import check_volume
from .checks.todos import check_todos
from .checks.glossary import check_glossary_coverage, check_glossary_sources
from .checks.meta_info import check_meta_info
from .checks.semantic_coverage import check_semantic_coverage


def load_documents(repo_root: str, rel_paths: List[str]) -> List[Document]:
    docs = []
    for rel in rel_paths:
        full = os.path.join(repo_root, rel)
        with open(full, encoding="utf-8") as fh:
            docs.append(parse_document(rel.replace("\\", "/"), fh.read()))
    return docs


def run(documents: List[Document], config: Config, existing_files=None,
        repo_root: str = None) -> List[Finding]:
    topo = Topology(documents, existing_files=existing_files)
    findings: List[Finding] = []

    for doc in documents:
        rules = config.rules_for(doc.path)
        if "links" in rules:
            findings += check_links(doc, topo)
        if "references" in rules:
            findings += check_references(doc)
        if "ids" in rules:
            findings += check_ids(doc)
        if "sections" in rules:
            findings += check_sections(doc)
        if "roles" in rules:
            findings += check_roles(doc)
        if "forbidden" in rules:
            findings += check_forbidden(doc)
        if "paths" in rules:
            findings += check_paths(doc)
        if "volume" in rules:
            findings += check_volume(doc, config)
        if "todos" in rules:
            findings += check_todos(doc)
        if "meta_info" in rules:
            findings += check_meta_info(doc)
        if repo_root is not None:
            findings += check_semantic_coverage(doc, repo_root)

    # glossary カバレッジ（cross-document）
    glossary = next((d for d in documents if classify(d.path) == "glossary"), None)
    if glossary is not None:
        core = [d for d in documents if classify(d.path) == "core"]
        findings += check_glossary_coverage(core, glossary)
        findings += check_glossary_sources(glossary, topo)

    findings.sort(key=lambda f: (f.path, f.line, f.rule_id))
    return findings, topo
