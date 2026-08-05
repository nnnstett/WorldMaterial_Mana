"""公理項目が意味検証ケースに被覆されているかのチェック。

`world/core/axioms.md` の項目アンカーのうち、`semantic-tests/public/cases/` のどの
`must.from` からも参照されていないものを warning で挙げる。全項目の被覆は目標ではない
（ケース化に適さない定義・補足を含む）ため error にしない。改訂で被覆が失われたことは
生成物 `semantic-tests/coverage.md` の差分で追う。
"""
from __future__ import annotations

import json
import os
import re
from typing import List

from ..report import Finding, Severity

_ANCHOR = re.compile(r'<a id="([^"]+)"')
_ITEM_REF = re.compile(r"^([EI]\d+)#(.+)$")

AXIOMS_REL = "world/core/axioms.md"
CASES_REL = "semantic-tests/public/cases"


def _referenced_anchors(repo_root: str) -> set:
    cases_dir = os.path.join(repo_root, CASES_REL)
    if not os.path.isdir(cases_dir):
        return set()
    refs = set()
    for name in sorted(os.listdir(cases_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(cases_dir, name), encoding="utf-8") as fh:
            case = json.load(fh)
        for item in case.get("key", {}).get("must", []):
            for ref in item.get("from", []):
                m = _ITEM_REF.match(ref)
                if m:
                    refs.add(f"{m.group(1).lower()}-{m.group(2)}")
    return refs


def check_semantic_coverage(doc, repo_root: str) -> List[Finding]:
    """axioms.md の項目のうち、意味検証ケースが根拠に挙げていないものを warning で挙げる。"""
    if doc.path != AXIOMS_REL:
        return []
    referenced = _referenced_anchors(repo_root)
    findings: List[Finding] = []
    for idx, raw in enumerate(doc.lines):
        for anchor in _ANCHOR.findall(raw):
            if anchor in referenced:
                continue
            findings.append(Finding(
                "semantic.uncovered-item", Severity.WARNING, doc.path, idx + 1,
                f"この項目を根拠に挙げる意味検証ケースがない: {anchor}",
            ))
    return findings
