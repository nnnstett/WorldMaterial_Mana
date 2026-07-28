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


class TestItemAnchors(unittest.TestCase):
    """公理項目の名前付きアンカー（<a id="..."></a>）のサポート。"""

    def test_html_anchor_collected(self):
        _, parsed = build({
            "world/core/axioms.md": '4. 魂は固有の大きさを持つ <a id="e5-大きさ"></a>\n',
        })
        self.assertIn("e5-大きさ", parsed[0].html_anchors)
        self.assertEqual(parsed[0].html_anchors["e5-大きさ"], 1)

    def test_link_to_item_anchor_resolves(self):
        topo, parsed = build({
            "world/core/axioms.md": '## [E5] 魂\n\n4. 魂は固有の大きさを持つ <a id="e5-大きさ"></a>\n',
            "world/core/theorems.md": "## [T2] 共鳴現化\n\n**導出元**: [E5 魂](axioms.md#e5-魂)\n\n**証明スケッチ**:\n- [E5 魂#大きさ](axioms.md#e5-大きさ) により上限が決まる\n",
        })
        findings = check_links(parsed[1], topo)
        self.assertEqual(findings, [])

    def test_link_to_missing_item_anchor_errors(self):
        topo, parsed = build({
            "world/core/axioms.md": "## [E5] 魂\n",
            "world/core/theorems.md": "[E5 魂#大きさ](axioms.md#e5-大きさ)\n",
        })
        findings = check_links(parsed[1], topo)
        self.assertTrue(any(f.rule_id == "links.missing-anchor" for f in findings))

    def test_item_anchor_id_mismatch(self):
        topo, parsed = build({
            "world/core/axioms.md": '## [E6] 精神エネルギー\n\n1. <a id="e6-発生"></a>発生する\n',
            "world/core/theorems.md": "[E5 魂#発生](axioms.md#e6-発生)\n",
        })
        findings = check_links(parsed[1], topo)
        self.assertTrue(any(f.rule_id == "links.id-mismatch" for f in findings))

    def test_anchor_in_code_fence_ignored(self):
        _, parsed = build({
            "a.md": '```\n<a id="e1-例"></a>\n```\n',
        })
        self.assertNotIn("e1-例", parsed[0].html_anchors)


class TestAnchorRobustness(unittest.TestCase):
    """アンカーの一意性・命名規則・所属群の検査。"""

    def test_duplicate_anchor_detected(self):
        topo, parsed = build({
            "world/core/axioms.md": '## [E5] 魂\n\n1. 一つ目 <a id="e5-孔"></a>\n2. 二つ目 <a id="e5-孔"></a>\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertTrue(any(f.rule_id == "links.duplicate-anchor" for f in findings))

    def test_anchor_heading_collision_detected(self):
        topo, parsed = build({
            "world/core/axioms.md": '## [E5] 魂\n\n1. 項目 <a id="e5-魂"></a>\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertTrue(any(f.rule_id == "links.duplicate-anchor" for f in findings))

    def test_anchor_owner_mismatch(self):
        topo, parsed = build({
            "world/core/axioms.md": '## [E6] 精神エネルギー\n\n1. 項目 <a id="e5-大きさ"></a>\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertTrue(any(f.rule_id == "links.anchor-owner-mismatch" for f in findings))

    def test_anchor_owner_match_ok(self):
        topo, parsed = build({
            "world/core/axioms.md": '## [E5] 魂\n\n1. 項目 <a id="e5-大きさ"></a>\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertEqual(findings, [])

    def test_non_item_anchor_in_core_flagged(self):
        topo, parsed = build({
            "world/core/axioms.md": '## [E5] 魂\n\n1. 項目 <a id="foo"></a>\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertTrue(any(f.rule_id == "links.anchor-format" for f in findings))

    def test_non_item_anchor_outside_core_ok(self):
        topo, parsed = build({
            "world/magic.md": '## 魔法\n\n本文 <a id="foo"></a>\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertEqual(findings, [])

    def test_headingless_section_link_no_false_fire(self):
        # [T4#還元判定] のような ID 無し見出しへのリンクは項目アンカー照合を発火させない
        topo, parsed = build({
            "world/core/theorems.md": '## [T4] マナ還元\n\n#### 還元判定\n\n[T4#還元判定](#還元判定)\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertEqual(findings, [])


_AXIOMS_E5 = '## [E5] 魂\n\n**公理**:\n1. 魂は固有の大きさを持つ <a id="e5-大きさ"></a>\n'


class TestItemAnchorScope(unittest.TestCase):
    """項目アンカー参照は world/ 配下でのみ使う（links.item-anchor-scope）。
    world/ 内での使い分け（依存の引用か純粋なポインタか）はレビューで判断する。"""

    def test_reference_inside_proof_sketch_ok(self):
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**導出元**: [E5 魂](axioms.md#e5-魂)\n\n"
                "**証明スケッチ**:\n"
                "- [E5 魂#大きさ](axioms.md#e5-大きさ) により上限が決まる\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_reference_in_detail_section_ok(self):
        # 証明スケッチ外（詳細・補足など）でも world/ 配下なら使える。
        # 依存の引用かポインタかの使い分けはレビューで判断する
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**証明スケッチ**:\n- ステップ\n\n"
                "**詳細**:\n- [E5 魂#大きさ](axioms.md#e5-大きさ) を参照\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_reference_outside_world_flagged(self):
        # world/ 配下以外（glossary.md・docs/ 等）では項目アンカー参照を使わない
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5,
            "glossary.md": "[E5 魂#大きさ](world/core/axioms.md#e5-大きさ)\n",
        })
        findings = check_links(parsed[1], topo)
        self.assertTrue(any(f.rule_id == "links.item-anchor-scope" for f in findings))

    def test_reference_from_applied_file_ok(self):
        # 応用ファイル（world/ 配下）では項目アンカー参照を使える
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5,
            "world/magic.md": "[E5 魂#大きさ](core/axioms.md#e5-大きさ)\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_group_link_outside_proof_ok(self):
        # 見出しアンカー（群単位リンク）は e5- で始まっても対象外
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**詳細**:\n- [E5 魂](axioms.md#e5-魂) を参照\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_shortcut_reference_in_proof_ok(self):
        # shortcut reference の定義行はリンク使用ではないため検査対象にならない
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**導出元**: [E5 魂](axioms.md#e5-魂)\n\n"
                "**証明スケッチ**:\n"
                "- [E5 魂#大きさ] により上限が決まる\n\n"
                "[E5 魂#大きさ]: axioms.md#e5-大きさ\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_subheading_after_proof_ok(self):
        # 証明スケッチの後の下位見出し（節）は証明スケッチではないため
        # 導出元 warning の対象にならず、参照自体は許可される
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**証明スケッチ**:\n- ステップ\n\n"
                "#### 特殊事例\n\n[E5 魂#大きさ](axioms.md#e5-大きさ) を参照\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_reference_from_readme_ok(self):
        # world/README.md（導出構造マップ）でも項目アンカー参照を許可する
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5,
            "world/README.md": "[E5 魂#大きさ](core/axioms.md#e5-大きさ)\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_proof_section_in_axiom_group_ok(self):
        # E/I エントリ内の「証明スケッチ」ラベルは導出元 warning の対象外（定理限定）で、
        # 参照自体は world/ 配下なので許可される
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5 +
                '\n### [E6] 精神エネルギー\n\n**証明スケッチ**:\n'
                "- [E5 魂#大きさ](#e5-大きさ) を参照\n",
        })
        self.assertEqual(check_links(parsed[0], topo), [])


class TestAnchorPlacement(unittest.TestCase):
    """項目アンカーは公理項目（番号付きリスト）の行末に置く（links.anchor-placement）。"""

    def test_anchor_at_line_end_ok(self):
        topo, parsed = build({"world/core/axioms.md": _AXIOMS_E5})
        self.assertEqual(check_links(parsed[0], topo), [])

    def test_anchor_at_item_start_flagged(self):
        topo, parsed = build({
            "world/core/axioms.md":
                '## [E5] 魂\n\n1. <a id="e5-大きさ"></a> 魂は固有の大きさを持つ\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertTrue(any(f.rule_id == "links.anchor-placement" for f in findings))

    def test_anchor_on_non_numbered_line_flagged(self):
        topo, parsed = build({
            "world/core/axioms.md":
                '## [E5] 魂\n\n魂は固有の大きさを持つ <a id="e5-大きさ"></a>\n',
        })
        findings = check_links(parsed[0], topo)
        self.assertTrue(any(f.rule_id == "links.anchor-placement" for f in findings))

    def test_anchor_outside_core_not_checked(self):
        topo, parsed = build({
            "world/magic.md": '## 魔法\n\n1. <a id="e5-大きさ"></a> 本文\n',
        })
        self.assertEqual(check_links(parsed[0], topo), [])


_AXIOMS_E5_I1 = (
    _AXIOMS_E5 +
    "\n## [I1] 変換則\n\n**公理**:\n1. 変換は量を保つ\n"
)


class TestItemAnchorDerivation(unittest.TestCase):
    """証明スケッチの項目アンカー参照は導出元の群に含まれる（links.item-anchor-derivation）。"""

    def test_referenced_group_in_derivation_ok(self):
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5_I1,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**導出元**: [E5 魂](axioms.md#e5-魂)\n\n"
                "**証明スケッチ**:\n- [E5 魂#大きさ](axioms.md#e5-大きさ) により上限が決まる\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_referenced_group_missing_from_derivation_warns(self):
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5_I1,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**導出元**: [I1 変換則](axioms.md#i1-変換則)\n\n"
                "**証明スケッチ**:\n- [E5 魂#大きさ](axioms.md#e5-大きさ) により上限が決まる\n",
        })
        findings = check_links(parsed[1], topo)
        hits = [f for f in findings if f.rule_id == "links.item-anchor-derivation"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].severity, Severity.WARNING)

    def test_group_link_not_counted(self):
        # 群単位リンク（見出しアンカー）は導出元包含の検査対象にしない
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5_I1,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**導出元**: [I1 変換則](axioms.md#i1-変換則)\n\n"
                "**証明スケッチ**:\n- [E5 魂](axioms.md#e5-魂) を参照\n",
        })
        findings = check_links(parsed[1], topo)
        self.assertFalse(
            any(f.rule_id == "links.item-anchor-derivation" for f in findings))

    def test_shortcut_derivation_ok(self):
        # 本番形式: 導出元が shortcut reference（末尾に参照定義）でも群を認識する
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5_I1,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**導出元**: [E5 魂] + [I1 変換則]\n\n"
                "**証明スケッチ**:\n- [E5 魂#大きさ] により上限が決まる\n\n"
                "[E5 魂]: axioms.md#e5-魂\n"
                "[I1 変換則]: axioms.md#i1-変換則\n"
                "[E5 魂#大きさ]: axioms.md#e5-大きさ\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])

    def test_multiline_derivation_ok(self):
        # 導出元セクションが複数行に折り返しても群を認識する
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS_E5_I1,
            "world/core/theorems.md":
                "## [T2] 共鳴現化\n\n**導出元**: [I1 変換則](axioms.md#i1-変換則) +\n"
                "[E5 魂](axioms.md#e5-魂)\n\n"
                "**証明スケッチ**:\n- [E5 魂#大きさ](axioms.md#e5-大きさ) により上限が決まる\n",
        })
        self.assertEqual(check_links(parsed[1], topo), [])
