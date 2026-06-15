"""メタ・制作情報の混入チェック（architecture.md §4.9 / world-doc-reviewer 観点 C7 の lint 昇格）。

`world/` 配下の本文（公理・定理・未解明領域・応用）と `glossary.md` は、
読者（中学生〜の興味読者・物語作者）向けの世界の記述に徹する。
制作・運用・設計のメタ情報を本文に書かない。これらは執筆者・レビュアー向けの
情報であり、メタ文書（`docs/`）に置く。

検出対象（本文中。コードブロック・引用 `>`・インラインコードは対象外）:
- **ツール・運用**: `scripts/` パス、`check.py`、`make check` / `make test`、
  CI ワークフロー（`.github`、`continue-on-error`、`lefthook`）
- **設計／規約／計画文書名**: `architecture.md`、`writing-rules.md`、
  `redesign-plan.md`、`design-notes.md`

例外:
- **README（ハブ）からの誘導リンク**: README は世界へのハブであり、
  `design-notes.md`・`architecture.md` への誘導は正規の導線として許容する
  （design-notes.md §0 / architecture.md §4.9）。README 以外の本文からは不可。
"""
from __future__ import annotations

import os
import re
from typing import List

from ..model import Document, iter_prose
from ..report import Finding, Severity

# 設計／規約／計画文書名（メタ文書）。
_META_DOC = re.compile(r"(architecture|writing-rules|redesign-plan|design-notes)\.md")

# README ハブからのみ許容するメタ文書（誘導リンクの対象）。
_README_ALLOWED = {"architecture.md", "design-notes.md"}

# ツール・運用トークン。日本語本文には本来現れない英字主体のトークンに限定し、
# 誤検出を避ける（「整合性チェック」等の一般語は対象にしない）。
_OPS_PATTERNS = [
    (re.compile(r"scripts/"), "scripts/ パス"),
    (re.compile(r"check\.py"), "check.py"),
    (re.compile(r"make\s+(?:check|test)"), "make check / make test"),
    (re.compile(r"continue-on-error"), "continue-on-error（CI 設定）"),
    (re.compile(r"lefthook"), "lefthook（フック設定）"),
    (re.compile(r"\.github"), ".github（CI ワークフロー）"),
]


def check_meta_info(doc: Document) -> List[Finding]:
    findings: List[Finding] = []
    is_readme = os.path.basename(doc.path) == "README.md"

    for line_no, text in iter_prose(doc):
        if text.lstrip().startswith(">"):
            continue

        for m in _META_DOC.finditer(text):
            doc_name = m.group(0)
            if is_readme and doc_name in _README_ALLOWED:
                continue
            findings.append(Finding(
                "meta-info.doc", Severity.ERROR, doc.path, line_no,
                f"メタ文書名「{doc_name}」への言及。設計・規約・計画文書は本文に書かない"
                "（architecture.md §4.9）",
            ))

        for pat, label in _OPS_PATTERNS:
            if pat.search(text):
                findings.append(Finding(
                    "meta-info.ops", Severity.ERROR, doc.path, line_no,
                    f"制作・運用情報「{label}」への言及。ツール・CI 等は本文に書かない"
                    "（architecture.md §4.9）",
                ))

    return findings
