"""チェック結果（Finding）の表現と整形。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    path: str
    line: int
    message: str

    def format(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.severity.value}] {self.rule_id} {loc}: {self.message}"


def summarize(findings: List[Finding]) -> str:
    errors = sum(1 for f in findings if f.severity is Severity.ERROR)
    warnings = sum(1 for f in findings if f.severity is Severity.WARNING)
    return f"{errors} error(s), {warnings} warning(s)"


def exit_code(findings: List[Finding]) -> int:
    """error が 1 件でもあれば 1。warning のみ・無しは 0。"""
    return 1 if any(f.severity is Severity.ERROR for f in findings) else 0
