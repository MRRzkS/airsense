"""Rule 3 — severity mapping and escalation.

Severity is a function of two things, not one: *where* the score sits and *how
fast it is moving*. A unit parked at 0.62 for a week and a unit that reached
0.62 this morning need different responses, and a band-only mapping cannot tell
them apart.

Rate of change therefore promotes a device one severity level. It never demotes
one — a unit that is bad but stable is still bad.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK: Final[dict[Severity, int]] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}

_BY_RANK: Final[tuple[Severity, ...]] = (
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)


def worst(left: Severity, right: Severity) -> Severity:
    """Return the more serious of two severities."""
    return left if left.rank >= right.rank else right


def rate_of_change(scores: Sequence[float]) -> float:
    """Average change in health index per sample across the window.

    Zero for fewer than two samples: one reading describes a position, not a
    trend, and inventing a slope from it would let a single spike promote a
    device's severity.
    """
    if len(scores) < 2:
        return 0.0
    return (scores[-1] - scores[0]) / (len(scores) - 1)


@dataclass(frozen=True, slots=True)
class SeverityPolicy:
    """Score bands, plus the slope at which a device is promoted one level."""

    medium_band: float
    high_band: float
    critical_band: float
    fast_degradation_per_sample: float

    def __post_init__(self) -> None:
        if not self.medium_band < self.high_band < self.critical_band:
            raise ValueError("severity bands must increase: medium < high < critical")
        if self.fast_degradation_per_sample <= 0:
            raise ValueError("fast_degradation_per_sample must be positive")

    def evaluate(self, score: float, recent_scores: Sequence[float]) -> Severity:
        """Map a score and its recent trajectory onto a severity."""
        base = self._band(score)
        if rate_of_change(recent_scores) >= self.fast_degradation_per_sample:
            return self._promote(base)
        return base

    def _band(self, score: float) -> Severity:
        if score >= self.critical_band:
            return Severity.CRITICAL
        if score >= self.high_band:
            return Severity.HIGH
        if score >= self.medium_band:
            return Severity.MEDIUM
        return Severity.LOW

    def _promote(self, severity: Severity) -> Severity:
        return _BY_RANK[min(severity.rank + 1, len(_BY_RANK) - 1)]
