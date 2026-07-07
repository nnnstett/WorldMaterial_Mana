"""設定（閾値・ファイルスコープ別ルール）。

ルールはファイルの役割ごとに出し分ける。メタ文書（docs/*）は禁止語・旧パス・
コードのみ参照などを意図的に含むため、内容系ルールの対象外とする。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_THRESHOLDS_PATH = os.path.join(_HERE, "thresholds.json")


def load_thresholds(path: str = _THRESHOLDS_PATH) -> Dict[str, int]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}


# スコープ: ファイルパス（リポジトリルート相対）→ 適用ルール集合
# "core": 公理・定理・未解明領域 / "applied": 応用 / "glossary" / "meta"
def classify(path: str) -> str:
    p = path.replace("\\", "/")
    if p.endswith("glossary.md"):
        return "glossary"
    if "/core/" in p and (
        p.endswith("axioms.md") or p.endswith("theorems.md") or p.endswith("open-questions.md")
    ):
        return "core"
    if p.startswith("docs/") or "/docs/" in p:
        return "meta"
    if p.startswith("world/") or "/world/" in p:
        return "applied"
    return "other"


# 各スコープで有効なルール ID
RULES_BY_SCOPE: Dict[str, List[str]] = {
    "core": [
        "links", "references", "ids", "sections", "roles",
        "forbidden", "paths", "volume", "todos", "meta_info",
    ],
    "applied": [
        "links", "references", "sections",
        "forbidden", "paths", "volume", "todos", "meta_info",
    ],
    "glossary": ["links", "forbidden", "paths", "meta_info"],
    # メタ文書（docs/）は設計上、禁止語・旧パス・コードのみ参照の NG 例を意図的に
    # 含むため、内容系ルールは対象外とする。リンクの実在だけは検査する
    # （規約文書間の相互参照が主な対象。例示リンクはコードスパンに入れる規約）
    "meta": ["links"],
    "other": ["links"],
}


@dataclass
class Config:
    thresholds: Dict[str, int] = field(default_factory=load_thresholds)

    def rules_for(self, path: str) -> List[str]:
        return RULES_BY_SCOPE.get(classify(path), ["links"])
