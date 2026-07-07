"""必須セクション・分量上限・TODO 散在チェックのテスト（TDD）。"""
import unittest

from doc_check.model import parse_document
from doc_check.config import Config
from doc_check.checks.sections import check_sections
from doc_check.checks.roles import check_roles
from doc_check.checks.volume import check_volume
from doc_check.checks.todos import check_todos
from doc_check.report import Severity


def rule_ids(findings):
    return [f.rule_id for f in findings]


AXIOM_OK = (
    "## 公理（存在に関するもの）\n\n"
    "### [E1] 現界\n\n"
    "物理法則に従う3次元時空（現界）が存在する。\n\n"
    "**公理**:\n1. 現界は物理法則に従う3次元時空である\n\n"
    "**補足**:\n- 詳細は読者の物理直感に委ねる。\n\n"
    "**関連**: → [E2 真界](#e2-真界)\n"
)

THEOREM_MISSING_DERIV = (
    "### [T1] エネルギー保存則\n\n"
    "**命題**: 総量は一定である。\n\n"
    "**関連**: → [T4 マナ還元](#t4-マナ還元)\n"
)


class TestSections(unittest.TestCase):
    def test_axiom_complete_ok(self):
        doc = parse_document("world/core/axioms.md", AXIOM_OK)
        self.assertEqual(check_sections(doc), [])

    def test_theorem_missing_derivation_flagged(self):
        doc = parse_document("world/core/theorems.md", THEOREM_MISSING_DERIV)
        ids = rule_ids(check_sections(doc))
        self.assertIn("sections.missing", ids)

    def test_axiom_missing_axiom_list_flagged(self):
        md = "### [E1] 現界\n\n**関連**: → [E2 真界](#e2-真界)\n"
        doc = parse_document("world/core/axioms.md", md)
        self.assertIn("sections.missing", rule_ids(check_sections(doc)))

    def test_axiom_forbidden_proposition_flagged(self):
        # 公理群に旧形式の 命題・詳細 は置けない
        md = (
            "### [E1] 現界\n\n**命題**: 存在する。\n\n"
            "**公理**:\n1. 存在する\n\n**関連**: → [E2 真界](#e2-真界)\n"
        )
        doc = parse_document("world/core/axioms.md", md)
        self.assertIn("sections.forbidden", rule_ids(check_sections(doc)))

    def test_theorem_forbidden_axiom_list_flagged(self):
        # 定理に「公理」リストは置けない
        md = (
            "### [T1] エネルギー保存則\n\n**命題**: 総量は一定である。\n\n"
            "**導出元**: [I1 変換則](axioms.md#i1-変換則)\n\n"
            "**公理**:\n1. 新たな仮定\n\n**関連**: → [T4 マナ還元](#t4-マナ還元)\n"
        )
        doc = parse_document("world/core/theorems.md", md)
        self.assertIn("sections.forbidden", rule_ids(check_sections(doc)))

    def test_applied_requires_premise_line(self):
        md = "# 魔法\n\n冒頭リンクの無い本文。\n"
        doc = parse_document("world/magic.md", md)
        self.assertIn("sections.missing-premise", rule_ids(check_sections(doc)))

    def test_applied_with_premise_ok(self):
        md = "*前提: [T7 魔法](core/theorems.md#t7-魔法)*\n\n# 魔法\n\n本文。\n"
        doc = parse_document("world/magic.md", md)
        self.assertNotIn("sections.missing-premise", rule_ids(check_sections(doc)))


class TestVolume(unittest.TestCase):
    def test_entry_length_excludes_reference_definitions(self):
        # 最終エントリの範囲はファイル末尾の参照定義ブロックを含むが、
        # 参照定義行（[label]: url）は本文ではないため字数に数えない
        refdefs = "\n".join(
            f"[ラベル{i} 見出し語{i}]: core/axioms.md#anchor-{i}" for i in range(120)
        )
        doc = parse_document(
            "world/core/theorems.md",
            "### [T9] 超能力\n\n**命題**: 短い。\n\n本文一行。\n\n" + refdefs + "\n",
        )
        findings = check_volume(doc, Config())
        self.assertFalse(
            any(f.rule_id == "volume.entry-length" for f in findings))

    def setUp(self):
        self.cfg = Config()

    def test_heading_depth_over_limit(self):
        md = "# a\n\n## b\n\n### c\n\n#### d\n\n##### e\n"
        doc = parse_document("world/magic.md", md)
        self.assertIn("volume.heading-depth", rule_ids(check_volume(doc, self.cfg)))

    def test_list_items_over_limit(self):
        items = "\n".join(f"- 項目{i}" for i in range(20))
        doc = parse_document("world/magic.md", items + "\n")
        self.assertIn("volume.list-items", rule_ids(check_volume(doc, self.cfg)))

    def test_proposition_too_many_sentences(self):
        md = "### [T1] エネルギー保存則\n\n**命題**: 一文目。二文目。三文目。\n"
        doc = parse_document("world/core/theorems.md", md)
        self.assertIn("volume.proposition", rule_ids(check_volume(doc, self.cfg)))

    def test_axiom_entry_between_thresholds_warns(self):
        # 公理群は 1500 字超で警告（グルーピング見直しシグナル）、2000 字まではエラーにしない
        body = "あ" * 1600
        md = f"### [E1] 現界\n\n**公理**:\n1. {body}\n\n**関連**: → [E2 真界](#e2-真界)\n"
        doc = parse_document("world/core/axioms.md", md)
        findings = check_volume(doc, self.cfg)
        heavy = [f for f in findings if f.rule_id == "volume.axiom-entry-heavy"]
        self.assertEqual(len(heavy), 1)
        self.assertIs(heavy[0].severity, Severity.WARNING)
        self.assertNotIn("volume.entry-length", rule_ids(findings))

    def test_axiom_entry_over_hard_limit_errors(self):
        body = "あ" * 2100
        md = f"### [E1] 現界\n\n**公理**:\n1. {body}\n\n**関連**: → [E2 真界](#e2-真界)\n"
        doc = parse_document("world/core/axioms.md", md)
        self.assertIn("volume.entry-length", rule_ids(check_volume(doc, self.cfg)))

    def test_applied_file_too_long(self):
        md = "# x\n" + "\n".join(["本文。"] * 500)
        doc = parse_document("world/magic.md", md)
        self.assertIn("volume.file-length", rule_ids(check_volume(doc, self.cfg)))

    def test_exemption_comment_suppresses(self):
        items = "<!-- check:length-exempt 列挙が必要 -->\n" + "\n".join(f"- 項目{i}" for i in range(20))
        doc = parse_document("world/magic.md", items + "\n")
        self.assertNotIn("volume.list-items", rule_ids(check_volume(doc, self.cfg)))

    def test_entry_chars_excludes_link_url(self):
        # 長いリンク URL/テキストは文字数カウントから除外され、誤検出しない
        long_anchor = "あ" * 400
        md = (
            "### [T5] 存在強度\n\n"
            "**命題**: 短い。\n\n"
            f"**関連**: → [T5 存在強度#{long_anchor}](core/theorems.md#{long_anchor})\n"
        )
        doc = parse_document("world/core/theorems.md", md)
        self.assertNotIn("volume.entry-length", rule_ids(check_volume(doc, self.cfg)))


class TestRoles(unittest.TestCase):
    def test_valid_axiom_group_ok(self):
        doc = parse_document("world/core/axioms.md", AXIOM_OK)
        self.assertEqual(check_roles(doc), [])

    def test_unknown_section_flagged(self):
        md = (
            "### [E1] 現界\n\n**公理**:\n1. 存在する\n\n"
            "**メモ**: 規約外のセクション。\n\n**関連**: → [E2 真界](#e2-真界)\n"
        )
        doc = parse_document("world/core/axioms.md", md)
        self.assertIn("roles.unknown-section", rule_ids(check_roles(doc)))

    def test_section_order_violation_flagged(self):
        md = (
            "### [E1] 現界\n\n**公理**:\n1. 存在する\n\n"
            "**空白**:\n- 未解明である（→ [Q3 真界の内部構造](open-questions.md#q3)）\n\n"
            "**定義**:\n- **用語**: 意味。\n\n**関連**: → [E2 真界](#e2-真界)\n"
        )
        doc = parse_document("world/core/axioms.md", md)
        self.assertIn("roles.section-order", rule_ids(check_roles(doc)))

    def test_blank_bullet_without_q_link_flagged(self):
        md = (
            "### [E1] 現界\n\n**公理**:\n1. 存在する\n\n"
            "**空白**:\n- 行き先のない空白。\n\n**関連**: → [E2 真界](#e2-真界)\n"
        )
        doc = parse_document("world/core/axioms.md", md)
        self.assertIn("roles.blank-missing-q", rule_ids(check_roles(doc)))

    def test_list_item_bold_lead_not_treated_as_section(self):
        # 箇条内の **見出し語**: はセクションとして扱わない
        md = (
            "### [E1] 現界\n\n**公理**:\n1. 存在する\n\n"
            "**定義**:\n- **真度**: 深い〜浅いのグラデーション。\n\n"
            "**関連**: → [E2 真界](#e2-真界)\n"
        )
        doc = parse_document("world/core/axioms.md", md)
        self.assertEqual(check_roles(doc), [])

    def test_theorem_roles_and_section_scope_ok(self):
        # 定理の役割セクション（定義・補足）と、節内の役割セクション
        # （観測事実・目安・空白）。固定順は節ごとにリセットされる
        md = (
            "### [T4] マナ還元\n\n"
            "**命題**: 還元は意図的にも起こせる。\n\n"
            "**導出元**: [I3 副産則](axioms.md#i3-副産則)\n\n"
            "**詳細**:\n- 導出される内容。\n\n"
            "**定義**:\n- **還元力**: 高められた実効的な結合力。\n\n"
            "**補足**:\n- 理解を助ける説明。\n\n"
            "#### 活性と不活性\n\n"
            "- 導出される内容。\n\n"
            "**観測事実**:\n- 観測される事項。\n\n"
            "**目安**:\n- 数十年〜数百年のオーダー。\n\n"
            "**空白**:\n- 未確認である（→ [Q13 不活性瘴気の再活性化](open-questions.md#q13)）\n\n"
            "**関連**: → [I3 副産則](axioms.md#i3-副産則)\n"
        )
        doc = parse_document("world/core/theorems.md", md)
        self.assertEqual(check_roles(doc), [])

    def test_definition_style_entry_ok(self):
        # 「行使形態の定義」節下の T は定義様式（定義・定義対象・関連）
        md = (
            "## 行使形態の定義\n\n"
            "### [T7] 魔法\n\n"
            "**定義**: 自身の精神エネルギーで行使する場合、これを「魔法」と呼ぶ。\n\n"
            "**定義対象**: [T2 共鳴現化](#t2-共鳴現化) の行使のうち自身の精神エネルギーによるもの\n\n"
            "**詳細**:\n- 効率は破格である。\n\n"
            "**関連**: → [T2 共鳴現化](#t2-共鳴現化)\n"
        )
        doc = parse_document("world/core/theorems.md", md)
        self.assertEqual(check_roles(doc), [])
        self.assertEqual(check_sections(doc), [])

    def test_definition_style_forbids_proposition_and_sketch(self):
        md = (
            "## 行使形態の定義\n\n"
            "### [T7] 魔法\n\n"
            "**定義**: これを「魔法」と呼ぶ。\n\n"
            "**定義対象**: [T2 共鳴現化](#t2-共鳴現化) の行使\n\n"
            "**命題**: 置けないセクション。\n\n"
            "**関連**: → [T2 共鳴現化](#t2-共鳴現化)\n"
        )
        doc = parse_document("world/core/theorems.md", md)
        self.assertIn("sections.forbidden", rule_ids(check_sections(doc)))
        self.assertIn("roles.unknown-section", rule_ids(check_roles(doc)))

    def test_theorem_outside_definition_h2_still_requires_proposition(self):
        md = (
            "## 導出される法則\n\n"
            "### [T1] エネルギー保存則\n\n"
            "**定義**: 定理側に命題が無いケース。\n\n"
            "**関連**: → [I1 変換則](axioms.md#i1-変換則)\n"
        )
        doc = parse_document("world/core/theorems.md", md)
        ids = rule_ids(check_sections(doc))
        self.assertIn("sections.missing", ids)

    def test_definition_main_part_sentence_limit(self):
        # 行使形態の定義の主部（**定義**）にも文数上限がかかる
        md = (
            "## 行使形態の定義\n\n"
            "### [T7] 魔法\n\n"
            "**定義**: 一文目。二文目。三文目。\n\n"
            "**定義対象**: [T2 共鳴現化](#t2-共鳴現化) の行使\n\n"
            "**関連**: → [T2 共鳴現化](#t2-共鳴現化)\n"
        )
        doc = parse_document("world/core/theorems.md", md)
        self.assertIn("volume.proposition", rule_ids(check_volume(doc, Config())))

    def test_theorem_section_order_reset_only_at_heading(self):
        # 節をまたがず同一スコープ内で順序が逆行したらエラー
        md = (
            "### [T4] マナ還元\n\n"
            "**命題**: 還元は意図的にも起こせる。\n\n"
            "**導出元**: [I3 副産則](axioms.md#i3-副産則)\n\n"
            "#### 活性と不活性\n\n"
            "**空白**:\n- 未確認である（→ [Q13 不活性瘴気の再活性化](open-questions.md#q13)）\n\n"
            "**観測事実**:\n- 観測される事項。\n\n"
            "**関連**: → [I3 副産則](axioms.md#i3-副産則)\n"
        )
        doc = parse_document("world/core/theorems.md", md)
        self.assertIn("roles.section-order", rule_ids(check_roles(doc)))


class TestTodos(unittest.TestCase):
    def test_todo_in_body_flagged(self):
        md = "# 魔法\n\n- [ ] 本文中の TODO\n\n## 本編\n"
        doc = parse_document("world/magic.md", md)
        self.assertIn("todos.scattered", rule_ids(check_todos(doc)))

    def test_todo_under_todo_section_ok(self):
        md = "# 魔法\n\n本文。\n\n## ToDo\n\n- [ ] あとで書く\n"
        doc = parse_document("world/magic.md", md)
        self.assertEqual(check_todos(doc), [])


if __name__ == "__main__":
    unittest.main()
