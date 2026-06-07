"""トポロジー構築とリンクチェックのテスト（TDD）。

リンクチェックは全ドキュメントのトポロジー（ファイル＋見出しアンカーのノードと
リンクのエッジ）を構築し、その上で解決可否・ID 整合を判定する。
"""
import unittest

from doc_check.model import parse_document
from doc_check.topology import Topology
from doc_check.checks.links import check_links
from doc_check.report import Severity


def build(docs):
    """{path: markdown} から Topology を構築。"""
    parsed = [parse_document(p, c) for p, c in docs.items()]
    return Topology(parsed), parsed


class TestTopology(unittest.TestCase):
    def test_nodes_have_file_anchors(self):
        topo, _ = build({
            "world/core/axioms.md": "## [E1] 現界\n",
        })
        self.assertIn("world/core/axioms.md", topo.anchors)
        self.assertIn("e1-現界", topo.anchors["world/core/axioms.md"])

    def test_resolve_relative_path_with_dotdot(self):
        topo, _ = build({
            "docs/architecture.md": "x",
            "world/core/axioms.md": "## [E1] 現界\n",
        })
        # docs/ から ../world/core/axioms.md は world/core/axioms.md に解決
        self.assertEqual(
            topo.resolve("docs/architecture.md", "../world/core/axioms.md"),
            "world/core/axioms.md",
        )

    def test_resolve_same_dir(self):
        topo, _ = build({
            "world/magic.md": "x",
            "world/core/theorems.md": "## [T1] エネルギー保存則\n",
        })
        self.assertEqual(
            topo.resolve("world/magic.md", "core/theorems.md"),
            "world/core/theorems.md",
        )

    def test_export_dict(self):
        topo, _ = build({"a.md": "## H\n\n[x](a.md#h)\n"})
        d = topo.to_dict()
        self.assertIn("nodes", d)
        self.assertIn("edges", d)


class TestLinkChecks(unittest.TestCase):
    def test_valid_link_no_finding(self):
        topo, parsed = build({
            "world/magic.md": "[T1 エネルギー保存則](core/theorems.md#t1-エネルギー保存則)\n",
            "world/core/theorems.md": "## [T1] エネルギー保存則\n",
        })
        findings = check_links(parsed[0], topo)
        self.assertEqual(findings, [])

    def test_missing_file(self):
        topo, parsed = build({
            "world/magic.md": "[x](core/nope.md#a)\n",
        })
        findings = check_links(parsed[0], topo)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "links.missing-file")
        self.assertEqual(findings[0].severity, Severity.ERROR)

    def test_missing_anchor(self):
        topo, parsed = build({
            "world/magic.md": "[T1 エネルギー保存則](core/theorems.md#t1-存在しない)\n",
            "world/core/theorems.md": "## [T1] エネルギー保存則\n",
        })
        findings = check_links(parsed[0], topo)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "links.missing-anchor")

    def test_id_mismatch(self):
        # リンクテキストは T1 だがアンカーは T2 の見出し
        topo, parsed = build({
            "world/magic.md": "[T1 エネルギー保存則](core/theorems.md#t2-共鳴現化)\n",
            "world/core/theorems.md": "## [T1] エネルギー保存則\n\n## [T2] 共鳴現化\n",
        })
        findings = check_links(parsed[0], topo)
        ids = [f.rule_id for f in findings]
        self.assertIn("links.id-mismatch", ids)

    def test_subsection_reference_skips_id_match(self):
        # 重要な帰結節（id_code 無し）への T5 参照は ID 照合をスキップ（誤検出しない）
        topo, parsed = build({
            "world/magic.md": "[T5#ビッグバン由来物質の還元不可能性](core/theorems.md#重要な帰結-ビッグバン由来物質の還元不可能性)\n",
            "world/core/theorems.md": "## [T5] 存在強度\n\n#### 重要な帰結: ビッグバン由来物質の還元不可能性\n",
        })
        findings = check_links(parsed[0], topo)
        self.assertEqual(findings, [])

    def test_external_link_skipped(self):
        topo, parsed = build({
            "README.md": "[releases](https://github.com/x/y/releases) [mail](mailto:a@b.c)\n",
        })
        self.assertEqual(check_links(parsed[0], topo), [])

    def test_root_absolute_path(self):
        topo, parsed = build({
            "README.md": "[ライセンス](/LICENSE.md)\n",
            "LICENSE.md": "# License\n",
        })
        self.assertEqual(check_links(parsed[0], topo), [])

    def test_same_file_anchor(self):
        topo, parsed = build({
            "world/core/axioms.md": "## [E1] 現界\n\n[E1 現界](#e1-現界)\n",
        })
        findings = check_links(parsed[0], topo)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
