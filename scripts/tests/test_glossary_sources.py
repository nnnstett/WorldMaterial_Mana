"""glossary 出典対応チェック（glossary.source-term-missing）のテスト。"""
import unittest

from doc_check.model import parse_document
from doc_check.topology import Topology
from doc_check.checks.glossary import check_glossary_sources
from doc_check.report import Severity

_AXIOMS = (
    "## [E2] 真界\n\n**公理**:\n"
    "1. 真界の内部ではマナに濃淡があり、自然には緩慢にしか変動しない\n\n"
    "## [E5] 魂\n\n**公理**:\n1. 魂は固有の大きさを持つ\n"
)


def build(docs):
    parsed = [parse_document(p, c) for p, c in docs.items()]
    return Topology(parsed), parsed


class TestGlossarySources(unittest.TestCase):
    def test_term_present_via_fragment_ok(self):
        # 「マナの濃淡」は E2 に「マナに濃淡」として現れる（「の」分解の断片で照合）
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS,
            "glossary.md":
                "| 概念 | 一言解説 | 出典 |\n|---|---|---|\n"
                "| **マナの濃淡** | 濃い薄いがある | [真界](world/core/axioms.md#e2-真界) |\n",
        })
        self.assertEqual(check_glossary_sources(parsed[1], topo), [])

    def test_term_absent_warns(self):
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS,
            "glossary.md":
                "| 概念 | 一言解説 | 出典 |\n|---|---|---|\n"
                "| **存在強度** | 度合い | [真界](world/core/axioms.md#e2-真界) |\n",
        })
        findings = check_glossary_sources(parsed[1], topo)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "glossary.source-term-missing")
        self.assertEqual(findings[0].severity, Severity.WARNING)

    def test_non_bold_rows_skipped(self):
        # 早見表など、太字の用語セルを持たない行は対象外
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS,
            "glossary.md":
                "| 属性 | 何で決まるか |\n|---|---|\n"
                "| 存在強度 | 裏付け [真界](world/core/axioms.md#e2-真界) |\n",
        })
        self.assertEqual(check_glossary_sources(parsed[1], topo), [])

    def test_link_outside_source_cell_ignored(self):
        # 解説セル内のリンクは出典として扱わない（出典セルのリンクのみ検査）
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS,
            "glossary.md":
                "| 概念 | 一言解説 | 出典 |\n|---|---|---|\n"
                "| **存在強度** | 真界（[真界](world/core/axioms.md#e2-真界)）に関わる度合い "
                "| [魂](world/core/axioms.md#e5-魂) |\n",
        })
        findings = check_glossary_sources(parsed[1], topo)
        self.assertEqual(len(findings), 1)
        self.assertIn("e5-魂", findings[0].message)

    def test_whole_file_source_searches_full_text(self):
        # アンカー無しのファイル出典は全文照合
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS,
            "glossary.md":
                "| 概念 | 一言解説 | 出典 |\n|---|---|---|\n"
                "| **濃淡** | 濃い薄い | [axioms.md](world/core/axioms.md) |\n",
        })
        self.assertEqual(check_glossary_sources(parsed[1], topo), [])

    def test_link_text_match_does_not_suppress_warning(self):
        # 用語がリンクテキストに含まれていても、出典先セクションに無ければ警告する
        # （リンクテキスト一致で照合をスキップする「短絡」が再導入されたら本テストが落ちる）
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS,  # E2 セクションに「存在強度」は無い
            "glossary.md":
                "| 概念 | 一言解説 | 出典 |\n|---|---|---|\n"
                "| **存在強度** | 度合い | [存在強度の正](world/core/axioms.md#e2-真界) |\n",
        })
        findings = check_glossary_sources(parsed[1], topo)
        self.assertTrue(
            any(f.rule_id == "glossary.source-term-missing" for f in findings))

    def test_shortcut_reference_source_cell_checked(self):
        # shortcut reference 形式の出典セル（URL を持たない）も検査対象になる
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS,
            "glossary.md":
                "| 概念 | 一言解説 | 出典 |\n|---|---|---|\n"
                "| **存在強度** | 度合い | [真界] |\n\n"
                "[真界]: world/core/axioms.md#e2-真界\n",
        })
        findings = check_glossary_sources(parsed[1], topo)
        self.assertTrue(
            any(f.rule_id == "glossary.source-term-missing" for f in findings))

    def test_shortcut_reference_source_cell_ok(self):
        topo, parsed = build({
            "world/core/axioms.md": _AXIOMS,
            "glossary.md":
                "| 概念 | 一言解説 | 出典 |\n|---|---|---|\n"
                "| **マナの濃淡** | 濃い薄い | [真界] |\n\n"
                "[真界]: world/core/axioms.md#e2-真界\n",
        })
        self.assertEqual(check_glossary_sources(parsed[1], topo), [])


if __name__ == "__main__":
    unittest.main()
