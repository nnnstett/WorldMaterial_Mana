"""Markdown のパースモデル。

世界設定ドキュメントを構造化し、各チェック・トポロジー構築の共通基盤とする。
stdlib のみで実装する（チェッカー本体をゼロ依存に保つため）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict

# 見出しテキスト先頭の ID コード（例: "[E1] 現界" → "E1"）
_ID_IN_HEADING = re.compile(r"\[([EITQ]\d+)\]")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_REF_DEF = re.compile(r"^\s*\[([^\]]+)\]:\s*(.+?)\s*$")
_SHORTCUT_REF = re.compile(r"\[([^\]]+)\]")
_INLINE_CODE = re.compile(r"`[^`]*`")
# 本文中の名前付きアンカー（公理項目アンカー。例: <a id="e5-大きさ"></a>）
_HTML_ANCHOR = re.compile(r'<a\s+id="([^"]+)"\s*>\s*</a>')


def slugify(text: str) -> str:
    """GitHub の見出しアンカー生成を再現する。

    1. 小文字化・前後空白除去
    2. HTML タグ除去
    3. 英数字・空白・ハイフン・アンダースコア以外（句読点・括弧等）を除去
    4. 空白をハイフンへ
    """
    s = text.strip().lower()
    s = re.sub(r"<[^>]+>", "", s)
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_ ":
            out.append(ch)
    return "".join(out).replace(" ", "-")


@dataclass
class Heading:
    level: int
    text: str
    anchor: str
    line: int
    id_code: Optional[str] = None


@dataclass
class Link:
    text: str
    target_file: str   # "" なら同一ファイル
    target_anchor: str  # "" ならアンカー無し（ファイルのみ）
    line: int
    is_reference: bool = False


@dataclass
class Document:
    path: str
    lines: List[str]
    line_is_code: List[bool]  # 各行がコードフェンス内か
    headings: List[Heading] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    ref_defs: Dict[str, str] = field(default_factory=dict)
    # 名前付きアンカー（アンカー名 → 初出行番号）
    html_anchors: Dict[str, int] = field(default_factory=dict)
    # 名前付きアンカーの全出現（重複・所属検査用）
    html_anchor_occurrences: List[tuple] = field(default_factory=list)


def mask_inline_code(text: str) -> str:
    """インラインコード span を同じ長さの空白で置き換える。"""
    return _INLINE_CODE.sub(lambda mo: " " * len(mo.group(0)), text)


def mask_links(text: str, ref_defs: Dict[str, str]) -> str:
    """インラインリンクと、定義済みショートカット参照を空白でマスクする。

    「正しくリンクとして書かれた ID」を除外し、裸の ID 参照だけを残すために使う。
    """
    text = _INLINE_LINK.sub(lambda mo: " " * len(mo.group(0)), text)

    def _mask_ref(mo):
        label = mo.group(1)
        if label in ref_defs:
            return " " * len(mo.group(0))
        return mo.group(0)

    return _SHORTCUT_REF.sub(_mask_ref, text)


def iter_prose(doc: "Document"):
    """本文行（見出し・参照定義・コードフェンスを除く）を
    (行番号, インラインコードをマスクした本文) で yield する。
    """
    for idx, raw in enumerate(doc.lines):
        if doc.line_is_code[idx]:
            continue
        if _HEADING.match(raw):
            continue
        if _REF_DEF.match(raw):
            continue
        yield idx + 1, mask_inline_code(raw)


def _split_target(target: str) -> tuple[str, str]:
    """リンク先文字列を (ファイル, アンカー) に分解する。"""
    # タイトル（"url title"）を落とす
    target = target.strip().split()[0] if target.strip() else ""
    if "#" in target:
        file_part, anchor = target.split("#", 1)
        return file_part, anchor
    return target, ""


def parse_document(path: str, content: str) -> Document:
    lines = content.split("\n")
    line_is_code = [False] * len(lines)

    doc = Document(path=path, lines=lines, line_is_code=line_is_code)

    in_fence = False
    seen_anchors: Dict[str, int] = {}
    shortcut_candidates = []  # (label, line_no)

    for idx, raw in enumerate(lines):
        line_no = idx + 1

        if _FENCE.match(raw):
            in_fence = not in_fence
            line_is_code[idx] = True
            continue
        if in_fence:
            line_is_code[idx] = True
            continue

        # 見出し
        m = _HEADING.match(raw)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            base = slugify(text)
            anchor = base
            if base in seen_anchors:
                seen_anchors[base] += 1
                anchor = f"{base}-{seen_anchors[base]}"
            else:
                seen_anchors[base] = 0
            id_match = _ID_IN_HEADING.search(text)
            doc.headings.append(
                Heading(
                    level=level,
                    text=text,
                    anchor=anchor,
                    line=line_no,
                    id_code=id_match.group(1) if id_match else None,
                )
            )
            continue

        # 参照定義（[label]: url）
        rd = _REF_DEF.match(raw)
        if rd:
            doc.ref_defs[rd.group(1)] = rd.group(2)
            continue

        # インラインコードをマスク（中のリンク・括弧を無効化）
        masked = _INLINE_CODE.sub(lambda mo: " " * len(mo.group(0)), raw)

        # 名前付きアンカー
        for am in _HTML_ANCHOR.finditer(masked):
            doc.html_anchors.setdefault(am.group(1), line_no)
            doc.html_anchor_occurrences.append((am.group(1), line_no))

        # インラインリンク [text](target)
        consumed_spans = []
        for lm in _INLINE_LINK.finditer(masked):
            text = lm.group(1)
            tfile, tanchor = _split_target(lm.group(2))
            doc.links.append(
                Link(text=text, target_file=tfile, target_anchor=tanchor, line=line_no)
            )
            consumed_spans.append((lm.start(), lm.end()))

        # インラインリンク部分を空白でマスクし、残る [label] をショートカット参照候補に
        masked2 = list(masked)
        for s, e in consumed_spans:
            for i in range(s, e):
                masked2[i] = " "
        masked2 = "".join(masked2)
        for sm in _SHORTCUT_REF.finditer(masked2):
            label = sm.group(1)
            shortcut_candidates.append((label, line_no))

    doc._shortcut_labels = shortcut_candidates  # type: ignore[attr-defined]

    # ショートカット参照を定義で解決
    for label, line_no in shortcut_candidates:
        if label in doc.ref_defs:
            tfile, tanchor = _split_target(doc.ref_defs[label])
            doc.links.append(
                Link(
                    text=label,
                    target_file=tfile,
                    target_anchor=tanchor,
                    line=line_no,
                    is_reference=True,
                )
            )

    return doc
