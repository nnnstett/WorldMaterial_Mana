"""保証マップ（docs/architecture.md §5.5）と実装の対応テスト。

規約とチェッカーのドリフトを閉じるメタテスト。
- 保証マップの「機械」行に載る全チェック ID が実装に存在すること
- 実装済みの全チェック ID が保証マップに載っていること
"""
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))  # scripts/tests → リポジトリルート
_ARCH = os.path.join(_REPO, "docs", "architecture.md")
_CHECKS = os.path.join(_REPO, "scripts", "doc_check", "checks")

# 実装ソース中のチェック ID（Finding の第一引数の文字列リテラル）
_PREFIXES = (
    "links", "references", "ids", "sections", "roles",
    "forbidden", "paths", "volume", "todos", "glossary", "meta-info",
)
_FINDING_ID = re.compile(
    r'"((?:' + "|".join(_PREFIXES) + r')\.[a-z-]+)"'
)
_MAPPED_ID = re.compile(r"`([a-z-]+\.[a-z-]+)`")


def implemented_ids():
    ids = set()
    for name in sorted(os.listdir(_CHECKS)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(_CHECKS, name), encoding="utf-8") as fh:
            ids |= set(_FINDING_ID.findall(fh.read()))
    return ids


def mapped_ids():
    with open(_ARCH, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"### 5\.5 保証マップ(.*?)(?:\n---|\Z)", text, re.S)
    if m is None:
        return None
    ids = set()
    for line in m.group(1).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # 保証列は「機械」または「機械（warning）」等の注記付き
        if len(cells) >= 3 and cells[1].startswith("機械"):
            ids |= set(_MAPPED_ID.findall(cells[2]))
    return ids


class TestAssuranceMap(unittest.TestCase):
    def test_map_section_exists(self):
        self.assertIsNotNone(mapped_ids(), "architecture.md に §5.5 保証マップが無い")

    def test_mapped_ids_are_implemented(self):
        impl = implemented_ids()
        extra = mapped_ids() - impl
        self.assertEqual(
            extra, set(),
            f"保証マップに載っているが実装が無いチェック ID: {sorted(extra)}",
        )

    def test_implemented_ids_are_mapped(self):
        mapped = mapped_ids()
        missing = implemented_ids() - mapped
        self.assertEqual(
            missing, set(),
            f"実装済みだが保証マップに載っていないチェック ID: {sorted(missing)}",
        )


if __name__ == "__main__":
    unittest.main()
