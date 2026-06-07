"""runner の統合テスト（TDD）。"""
import unittest

from doc_check.model import parse_document
from doc_check.config import Config
from doc_check.runner import run


def docs_from(mapping):
    return [parse_document(p, c) for p, c in mapping.items()]


class TestRunner(unittest.TestCase):
    def test_clean_set_no_findings(self):
        docs = docs_from({
            "world/core/theorems.md": (
                "## [T1] エネルギー保存則\n\n"
                "**命題**: 総量は一定である。\n\n"
                "**導出元**: [I1 変換則](axioms.md#i1-変換則)\n\n"
                "**関連**: → [T4 マナ還元](#t4-マナ還元)\n\n"
                "## [T4] マナ還元\n\n"
                "**命題**: 瘴気が結合してマナに戻る。\n\n"
                "**導出元**: [I3 副産則](axioms.md#i3-副産則)\n\n"
                "**関連**: → [T1 エネルギー保存則](#t1-エネルギー保存則)\n"
            ),
            "world/core/axioms.md": (
                "## [I1] 変換則\n\n**命題**: 変換される。\n\n**関連**: → [I3 副産則](#i3-副産則)\n\n"
                "## [I3] 副産則\n\n**命題**: 瘴気が生じる。\n\n**関連**: → [I1 変換則](#i1-変換則)\n"
            ),
        })
        findings, topo = run(docs, Config())
        self.assertEqual([f.format() for f in findings], [])

    def test_detects_cross_file_broken_link(self):
        docs = docs_from({
            "world/magic.md": (
                "*前提: [T7 魔法](core/theorems.md#t7-魔法)*\n\n# 魔法\n\n本文。\n"
            ),
        })
        findings, _ = run(docs, Config())
        self.assertTrue(any(f.rule_id == "links.missing-file" for f in findings))

    def test_meta_doc_skips_content_rules(self):
        # docs/ は禁止語・旧パスを意図的に含むが、内容系ルールは適用しない
        docs = docs_from({
            "docs/architecture.md": "補題や系について述べる。character/ の旧パスも。\n",
        })
        findings, _ = run(docs, Config())
        ids = [f.rule_id for f in findings]
        self.assertNotIn("forbidden.term", ids)
        self.assertNotIn("paths.old-path", ids)


if __name__ == "__main__":
    unittest.main()
