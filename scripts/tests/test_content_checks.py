"""参照形式・ID 一意性・禁止語・旧パス検出のテスト（TDD）。"""
import unittest

from doc_check.model import parse_document
from doc_check.checks.references import check_references
from doc_check.checks.ids import check_ids
from doc_check.checks.forbidden import check_forbidden
from doc_check.checks.paths import check_paths


def rule_ids(findings):
    return [f.rule_id for f in findings]


class TestReferences(unittest.TestCase):
    def test_inline_link_ok(self):
        doc = parse_document(
            "world/magic.md",
            "[T1 エネルギー保存則](core/theorems.md#t1-エネルギー保存則) を参照。\n",
        )
        self.assertEqual(check_references(doc), [])

    def test_shortcut_ref_with_def_ok(self):
        doc = parse_document(
            "world/magic.md",
            "[T1 エネルギー保存則] を参照。\n\n[T1 エネルギー保存則]: core/theorems.md#t1-エネルギー保存則\n",
        )
        self.assertEqual(check_references(doc), [])

    def test_range_expression_ok(self):
        doc = parse_document(
            "world/core/theorems.md",
            "T1-T6 は本ファイルで完結し、T7-T9 は命題のみ記す。\n",
        )
        self.assertEqual(check_references(doc), [])

    def test_bare_code_in_prose_flagged(self):
        doc = parse_document("world/core/theorems.md", "T2 により瘴気が生じる。\n")
        self.assertIn("references.bare-code", rule_ids(check_references(doc)))

    def test_bare_bracket_flagged(self):
        doc = parse_document("world/magic.md", "詳細は [T1] を参照。\n")
        self.assertIn("references.bare-bracket", rule_ids(check_references(doc)))

    def test_code_fence_ignored(self):
        doc = parse_document(
            "world/magic.md",
            "```\nT2 により\n```\n",
        )
        self.assertEqual(check_references(doc), [])


class TestIds(unittest.TestCase):
    def test_unique_ok(self):
        doc = parse_document("world/core/axioms.md", "## [E1] 現界\n\n## [E2] 真界\n")
        self.assertEqual(check_ids(doc), [])

    def test_duplicate_flagged(self):
        doc = parse_document("world/core/axioms.md", "## [E1] 現界\n\n## [E1] 重複\n")
        self.assertIn("ids.duplicate", rule_ids(check_ids(doc)))


class TestForbidden(unittest.TestCase):
    def test_lemma_word_flagged(self):
        doc = parse_document("world/core/theorems.md", "これは補題である。\n")
        self.assertIn("forbidden.term", rule_ids(check_forbidden(doc)))

    def test_old_code_flagged(self):
        doc = parse_document("world/core/theorems.md", "かつて C2 と呼ばれた。\n")
        self.assertIn("forbidden.code", rule_ids(check_forbidden(doc)))

    def test_taikei_not_flagged(self):
        # 「体系」「分類体系」の 系 は誤検出しない
        doc = parse_document("world/core/theorems.md", "分類体系を維持する。\n")
        self.assertEqual(check_forbidden(doc), [])

    def test_dungeon_class_not_flagged(self):
        # ダンジョン分類 C-1 は旧 ID コードではない
        doc = parse_document("world/dungeons.md", "C-1 魔物の巣型。\n")
        self.assertEqual(check_forbidden(doc), [])

    def test_code_fence_ignored(self):
        doc = parse_document("world/core/theorems.md", "```\n補題\n```\n")
        self.assertEqual(check_forbidden(doc), [])


class TestPaths(unittest.TestCase):
    def test_old_path_flagged(self):
        doc = parse_document("world/magic.md", "詳細は [x](世界の法則.md) を参照。\n")
        self.assertIn("paths.old-path", rule_ids(check_paths(doc)))

    def test_old_dir_flagged(self):
        doc = parse_document("world/magic.md", "[種族](../character/種族.md)\n")
        self.assertIn("paths.old-path", rule_ids(check_paths(doc)))

    def test_dungeons_new_path_ok(self):
        doc = parse_document("world/magic.md", "[ダンジョン](dungeons.md)\n")
        self.assertEqual(check_paths(doc), [])


if __name__ == "__main__":
    unittest.main()
