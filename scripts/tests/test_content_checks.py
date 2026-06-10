"""参照形式・ID 一意性・禁止語・旧パス検出のテスト（TDD）。"""
import unittest

from doc_check.model import parse_document
from doc_check.checks.references import check_references
from doc_check.checks.ids import check_ids
from doc_check.checks.forbidden import check_forbidden
from doc_check.checks.paths import check_paths
from doc_check.checks.meta_info import check_meta_info


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

    def test_range_expression_flagged(self):
        # 範囲・列挙の例外は廃止。特定命題を指す場合は両端をリンクで書く。
        doc = parse_document(
            "world/core/theorems.md",
            "T1-T6 は本ファイルで完結し、T7-T9 は命題のみ記す。\n",
        )
        self.assertIn("references.bare-code", rule_ids(check_references(doc)))

    def test_enumeration_flagged(self):
        # 「T1, T5, T7」のような特定命題の列挙も対象。ID 採番例示の必要があるなら meta スコープで書く。
        doc = parse_document(
            "world/core/theorems.md",
            "対象は T1, T5, T7 である。\n",
        )
        ids = rule_ids(check_references(doc))
        self.assertEqual(ids.count("references.bare-code"), 3)

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


class TestMetaInfo(unittest.TestCase):
    def test_meta_doc_name_flagged(self):
        doc = parse_document(
            "world/magic.md",
            "詳細は [設計指針](../docs/architecture.md) を参照。\n",
        )
        self.assertIn("meta-info.doc", rule_ids(check_meta_info(doc)))

    def test_writing_rules_flagged(self):
        doc = parse_document("world/magic.md", "writing-rules.md に従う。\n")
        self.assertIn("meta-info.doc", rule_ids(check_meta_info(doc)))

    def test_ops_scripts_flagged(self):
        doc = parse_document("world/magic.md", "scripts/check.py で検証する。\n")
        ids = rule_ids(check_meta_info(doc))
        self.assertIn("meta-info.ops", ids)

    def test_ops_make_check_flagged(self):
        doc = parse_document("glossary.md", "make check を実行する。\n")
        self.assertIn("meta-info.ops", rule_ids(check_meta_info(doc)))

    def test_readme_design_notes_link_ok(self):
        # README ハブからの design-notes 誘導リンクは許容
        doc = parse_document(
            "world/README.md",
            "改変ポイントは [design-notes](../docs/design-notes.md) を参照。\n",
        )
        self.assertEqual(check_meta_info(doc), [])

    def test_readme_architecture_link_ok(self):
        doc = parse_document(
            "world/README.md",
            "設計指針は [architecture](../docs/architecture.md) を参照。\n",
        )
        self.assertEqual(check_meta_info(doc), [])

    def test_readme_writing_rules_still_flagged(self):
        # README 例外は design-notes / architecture のみ。他メタ文書・ツール語は検出
        doc = parse_document(
            "world/README.md",
            "[規約](../docs/writing-rules.md) と scripts/check.py。\n",
        )
        ids = rule_ids(check_meta_info(doc))
        self.assertIn("meta-info.doc", ids)
        self.assertIn("meta-info.ops", ids)

    def test_general_term_not_flagged(self):
        # 一般語「整合性チェック」は誤検出しない
        doc = parse_document("glossary.md", "全体の整合性チェックを助ける索引。\n")
        self.assertEqual(check_meta_info(doc), [])

    def test_code_fence_ignored(self):
        doc = parse_document("world/magic.md", "```\nmake check\n```\n")
        self.assertEqual(check_meta_info(doc), [])

    def test_quote_ignored(self):
        doc = parse_document("world/magic.md", "> scripts/check.py の引用。\n")
        self.assertEqual(check_meta_info(doc), [])


if __name__ == "__main__":
    unittest.main()
