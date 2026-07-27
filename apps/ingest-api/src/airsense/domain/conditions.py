"""Rule 1 — hysteresis and debounce.

A degradation score is noisy. Transitioning the moment it crosses a line
produces a device that flaps between NORMAL and ALERT every few seconds, which
trains operators to ignore the console and buries the one transition that
mattered.

Two mechanisms, both required:

* **Debounce.** A transition needs `sustained_samples` consecutive readings on
  the far side of the threshold. One spike changes nothing.
* **Hysteresis.** The score must fall *meaningfully* below the entry threshold
  before the state relaxes, not merely back across it. Without the deadband a
  score oscillating around a single value satisfies the debounce in both
  directions and flaps anyway.

Escalation is fast and de-escalation is slow, deliberately: a unit degrading
quickly may jump NORMAL to ALERT in one transition, but recovery always steps
back one level at a time. Being late to stand down is cheap; being late to
raise an alarm is the failure this system exists to prevent.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum


class DeviceCondition(StrEnum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    ALERT = "ALERT"


@dataclass(frozen=True, slots=True)
class ConditionState:
    """What the system remembers about one device between readings."""

    condition: DeviceCondition = DeviceCondition.NORMAL
    recent_scores: tuple[float, ...] = ()

    def with_score(self, score: float, *, keep: int) -> "ConditionState":
        """Append a score, retaining at most `keep` of the most recent."""
        return replace(self, recent_scores=(*self.recent_scores, score)[-keep:])

    def at(self, condition: DeviceCondition) -> "ConditionState":
        return replace(self, condition=condition)


@dataclass(frozen=True, slots=True)
class ConditionPolicy:
    """Thresholds governing condition transitions.

    Entry thresholds must sit strictly above their matching exit thresholds;
    the gap between them is the deadband.
    """

    watch_enter: float
    watch_exit: float
    alert_enter: float
    alert_exit: float
    sustained_samples: int

    def __post_init__(self) -> None:
        if not self.watch_exit < self.watch_enter:
            raise ValueError("watch_exit must sit below watch_enter to form a deadband")
        if not self.alert_exit < self.alert_enter:
            raise ValueError("alert_exit must sit below alert_enter to form a deadband")
        if not self.watch_enter <= self.alert_enter:
            raise ValueError("alert_enter must not sit below watch_enter")
        if self.sustained_samples < 1:
            raise ValueError("sustained_samples must be at least 1")

    def evaluate(self, current: DeviceCondition, recent_scores: Sequence[float]) -> DeviceCondition:
        """Return the condition justified by the most recent scores.

        `recent_scores` is oldest-first. Fewer than `sustained_samples` scores
        is not evidence of anything, so the current condition is held.
        """
        if len(recent_scores) < self.sustained_samples:
            return current

        window = recent_scores[-self.sustained_samples :]

        if all(score >= self.alert_enter for score in window):
            return DeviceCondition.ALERT
        if current is DeviceCondition.NORMAL and all(score >= self.watch_enter for score in window):
            return DeviceCondition.WATCH

        if current is DeviceCondition.ALERT and all(score < self.alert_exit for score in window):
            return DeviceCondition.WATCH
        if current is DeviceCondition.WATCH and all(score < self.watch_exit for score in window):
            return DeviceCondition.NORMAL

        return current
