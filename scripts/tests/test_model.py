"""model.py のテスト（TDD: 先にテストを書く）。

slugify は GitHub の Markdown 見出しアンカー生成を再現する。
既知の対応（docs/architecture.md のリンク定義より）を正とする。
"""
import unittest

from doc_check.model import slugify, parse_document


class TestSlugify(unittest.TestCase):
    def test_ascii_with_id_prefix(self):
        # `### [E1] 現界` の見出しテキストは "[E1] 現界"
        self.assertEqual(slugify("[E1] 現界"), "e1-現界")

    def test_theorem_heading(self):
        self.assertEqual(slugify("[T1] エネルギー保存則"), "t1-エネルギー保存則")

    def test_colon_and_space(self):
        self.assertEqual(
            slugify("重要な帰結: ビッグバン由来物質の還元不可能性"),
            "重要な帰結-ビッグバン由来物質の還元不可能性",
        )

    def test_fullwidth_parens_and_ascii_letter(self):
        # `）` の前後に空白はないため "c" の後にハイフンは入らない
        self.assertEqual(
            slugify("[Q2] 意思を持つ道具（ケース C）の発生原理"),
            "q2-意思を持つ道具ケース-cの発生原理",
        )

    def test_fullwidth_parens_q5(self):
        self.assertEqual(
            slugify("[Q5] 複数現界（並行世界）の有無"),
            "q5-複数現界並行世界の有無",
        )

    def test_plain_japanese(self):
        self.assertEqual(slugify("術式の定義"), "術式の定義")

    def test_hyphen_preserved(self):
        self.assertEqual(slugify("A-1 魔物集結型"), "a-1-魔物集結型")


class TestParseHeadings(unittest.TestCase):
    def test_extracts_headings_with_levels_and_anchors(self):
        md = "# Title\n\n## [E1] 現界\n\n本文\n\n### 詳細\n"
        doc = parse_document("axioms.md", md)
        headings = doc.headings
        self.assertEqual([h.level for h in headings], [1, 2, 3])
        self.assertEqual(headings[1].text, "[E1] 現界")
        self.assertEqual(headings[1].anchor, "e1-現界")
        self.assertEqual(headings[1].id_code, "E1")
        self.assertIsNone(headings[2].id_code)

    def test_duplicate_headings_get_counter_suffix(self):
        md = "## 詳細\n\n## 詳細\n"
        doc = parse_document("x.md", md)
        self.assertEqual([h.anchor for h in doc.headings], ["詳細", "詳細-1"])


class TestParseLinks(unittest.TestCase):
    def test_inline_link(self):
        md = "本文 [T1 エネルギー保存則](theorems.md#t1-エネルギー保存則) です。\n"
        doc = parse_document("magic.md", md)
        self.assertEqual(len(doc.links), 1)
        link = doc.links[0]
        self.assertEqual(link.text, "T1 エネルギー保存則")
        self.assertEqual(link.target_file, "theorems.md")
        self.assertEqual(link.target_anchor, "t1-エネルギー保存則")

    def test_same_file_anchor_link(self):
        md = "[E1 現界](#e1-現界)\n"
        doc = parse_document("axioms.md", md)
        link = doc.links[0]
        self.assertEqual(link.target_file, "")
        self.assertEqual(link.target_anchor, "e1-現界")

    def test_reference_style_link(self):
        md = "本文 [T1 エネルギー保存則] を参照。\n\n[T1 エネルギー保存則]: theorems.md#t1-エネルギー保存則\n"
        doc = parse_document("magic.md", md)
        # shortcut reference は定義を解決して通常リンク扱い
        resolved = [l for l in doc.links if l.target_file or l.target_anchor]
        self.assertTrue(any(l.target_anchor == "t1-エネルギー保存則" for l in resolved))

    def test_links_inside_code_fence_are_ignored(self):
        md = "```\n[T1 エネルギー保存則](theorems.md#t1-エネルギー保存則)\n```\n"
        doc = parse_document("x.md", md)
        self.assertEqual(doc.links, [])

    def test_links_inside_inline_code_are_ignored(self):
        md = "`[T1](theorems.md#t1)` はコード。\n"
        doc = parse_document("x.md", md)
        self.assertEqual(doc.links, [])


if __name__ == "__main__":
    unittest.main()
