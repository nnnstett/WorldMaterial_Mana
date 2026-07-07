"""glossary 整合性チェック。

- glossary.missing: core ファイル（axioms/theorems/open-questions）に定義された
  全 ID が glossary.md に登場すること
- glossary.source-term-missing (warning): エントリの見出し語が出典リンク先
  セクション（見出し行を含む）の本文に現れること（writing-rules §6。出典の
  追従漏れと未接地の別名の近似検出。用語は括弧注記の除去・助詞等での分解・
  「の」「・」を無視した正規化で緩く照合する。2 字以上の断片が作れない短い
  用語は 1 字断片まで許すため、見逃しは残る近似である。リンクテキストとの
  一致は合格条件にしない — 出典先の実内容を保証しないため）
"""
from __future__ import annotations

import re
from typing import List

from ..model import Document
from ..report import Finding, Severity
from ..topology import Topology

# glossary テーブルの用語行: | **概念** | 一言解説 | 出典 |
_TERM_ROW = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|")


def check_glossary_coverage(core_docs: List[Document], glossary: Document) -> List[Finding]:
    text = "\n".join(glossary.lines)
    findings: List[Finding] = []
    for doc in core_docs:
        for h in doc.headings:
            if not h.id_code:
                continue
            if not re.search(rf"\b{re.escape(h.id_code)}\b", text):
                findings.append(Finding(
                    "glossary.missing", Severity.ERROR, glossary.path, 1,
                    f"{h.id_code}（{doc.path}）が glossary.md に未登録",
                ))
    return findings


# 用語を分解する区切り（助詞・記号）。「による」は「の」より先に評価する
_TERM_SPLIT = re.compile(r"による|[・のとがを＝／/\s]")
# 照合時に無視する文字（表記ゆれ吸収: 「マナの濃淡」⇔「マナに濃淡」等は候補分解で拾う）
_NORMALIZE = re.compile(r"[の・\s　]")


def _term_candidates(term: str) -> List[str]:
    """照合候補: 用語全体・括弧注記を除いた本体・助詞等で分解した断片（2 字以上）。

    2 字以上の断片が一つも作れない短い用語は、1 字の断片まで許す（緩い判定）。
    """
    parts = {term}
    base = re.sub(r"[（(].*?[)）]", "", term).strip()
    if base:
        parts.add(base)
    fragments = set()
    for t in (term, base):
        for seg in _TERM_SPLIT.split(t):
            seg = seg.strip()
            if seg:
                fragments.add(seg)
    long_fragments = {f for f in fragments if len(f) >= 2}
    parts |= long_fragments if long_fragments else fragments
    return sorted(parts, key=len, reverse=True)


def _match(candidates: List[str], text: str) -> bool:
    normalized = _NORMALIZE.sub("", text)
    return any(
        c in text or _NORMALIZE.sub("", c) in normalized for c in candidates
    )


def _section_text(doc: Document, anchor: str) -> str:
    """アンカー（見出し）が指すセクションの本文（見出し行を含む）。アンカー無しは全文。"""
    if not anchor:
        return "\n".join(doc.lines)
    for idx, h in enumerate(doc.headings):
        if h.anchor != anchor:
            continue
        end = len(doc.lines)
        for nxt in doc.headings[idx + 1:]:
            if nxt.level <= h.level:
                end = nxt.line - 1
                break
        return "\n".join(doc.lines[h.line - 1:end])
    return ""  # 見出しに解決しない（項目アンカー等）。実在は links 検査が担う


def check_glossary_sources(glossary: Document, topo: Topology) -> List[Finding]:
    findings: List[Finding] = []
    links_by_line: dict = {}
    for link in glossary.links:
        links_by_line.setdefault(link.line, []).append(link)

    for idx, raw in enumerate(glossary.lines):
        if glossary.line_is_code[idx]:
            continue
        m = _TERM_ROW.match(raw)
        if not m:
            continue
        term = m.group(1).strip()
        cells = raw.strip().strip("|").split("|")
        if len(cells) < 3:
            continue
        source_cell = cells[-1]

        for link in links_by_line.get(idx + 1, []):
            if "://" in link.target_file or link.target_file.startswith("mailto:"):
                continue
            # 出典セル内のリンクだけを出典として扱う（解説セル内のリンクは対象外）。
            # shortcut reference はセルに URL を持たないため [リンクテキスト] で判定する
            if link.is_reference:
                in_source_cell = f"[{link.text}]" in source_cell
            else:
                key = link.target_file + (
                    f"#{link.target_anchor}" if link.target_anchor else "")
                in_source_cell = key in source_cell
            if not in_source_cell:
                continue
            candidates = _term_candidates(term)
            target_path = topo.resolve(glossary.path, link.target_file)
            tdoc = topo.documents.get(target_path)
            if tdoc is None:
                continue  # ファイル不在は links.missing-file が報告する
            section = _section_text(tdoc, link.target_anchor)
            if not section:
                continue
            if not _match(candidates, section):
                findings.append(Finding(
                    "glossary.source-term-missing", Severity.WARNING,
                    glossary.path, idx + 1,
                    f"「{term}」の出典（{target_path}#{link.target_anchor}）の"
                    f"本文に見出し語が見当たらない（出典が古いか、見出し語が"
                    f"出典側に未接地。出典本文へ語を足すか、見出し語を出典の語に"
                    f"合わせる → writing-rules §6）",
                ))
    return findings
