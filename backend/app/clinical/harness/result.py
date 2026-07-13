"""Result types for the validation harness."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CheckResult:
    check: str
    passed: bool
    hard_stop: bool = True  # a §16F hard-stop failure blocks automated-screened serving
    messages: list[str] = field(default_factory=list)


@dataclass
class HarnessReport:
    item_id: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(r for r in self.results if not r.passed and r.hard_stop)

    @property
    def hard_stop_failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.hard_stop]

    @property
    def warnings(self) -> list[str]:
        out: list[str] = []
        for r in self.results:
            if not r.passed and not r.hard_stop:
                out.extend(r.messages)
        return out

    def failing_checks(self) -> list[str]:
        return [r.check for r in self.results if not r.passed and r.hard_stop]

    def as_dict(self) -> dict:
        return {
            "itemId": self.item_id,
            "passed": self.passed,
            "hardStopFailures": [
                {"check": r.check, "messages": r.messages} for r in self.hard_stop_failures
            ],
            "warnings": self.warnings,
            "checks": [
                {"check": r.check, "passed": r.passed, "hardStop": r.hard_stop, "messages": r.messages}
                for r in self.results
            ],
        }
