"""Rule 1 — hysteresis and debounce.

The rule exists to stop one noisy sample producing a state transition, and to
stop a score hovering on a threshold producing a stream of them.
"""

from itertools import pairwise

import pytest

from airsense.domain.conditions import ConditionPolicy, ConditionState, DeviceCondition

POLICY = ConditionPolicy(
    watch_enter=0.50,
    watch_exit=0.40,
    alert_enter=0.75,
    alert_exit=0.65,
    sustained_samples=3,
)

NORMAL = DeviceCondition.NORMAL
WATCH = DeviceCondition.WATCH
ALERT = DeviceCondition.ALERT


def run(scores: list[float], start: DeviceCondition = NORMAL) -> list[DeviceCondition]:
    """Feed scores one at a time, returning the condition after each."""
    state = ConditionState(condition=start)
    conditions = []
    for score in scores:
        state = state.with_score(score, keep=20)
        state = state.at(POLICY.evaluate(state.condition, state.recent_scores))
        conditions.append(state.condition)
    return conditions


# ─── Policy validity ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"watch_exit": 0.60}, "watch_exit must sit below watch_enter"),
        ({"alert_exit": 0.80}, "alert_exit must sit below alert_enter"),
        # Both alert thresholds move together: dropping only alert_enter would
        # trip the deadband check first and never reach the ordering check.
        ({"alert_enter": 0.45, "alert_exit": 0.30}, "alert_enter must not sit below watch_enter"),
        ({"sustained_samples": 0}, "sustained_samples must be at least 1"),
    ],
)
def test_an_incoherent_policy_is_rejected(overrides: dict[str, float], message: str) -> None:
    kwargs: dict[str, float] = {
        "watch_enter": 0.50,
        "watch_exit": 0.40,
        "alert_enter": 0.75,
        "alert_exit": 0.65,
        "sustained_samples": 3,
        **overrides,
    }
    with pytest.raises(ValueError, match=message):
        ConditionPolicy(**kwargs)  # type: ignore[arg-type]


# ─── Debounce ─────────────────────────────────────────────────────────────


def test_a_single_spike_changes_nothing() -> None:
    # The defect this rule exists to prevent: one bad sample opening a ticket.
    assert run([0.1, 0.1, 0.99, 0.1, 0.1]) == [NORMAL] * 5


def test_two_spikes_short_of_the_window_still_change_nothing() -> None:
    assert run([0.1, 0.99, 0.99, 0.1]) == [NORMAL] * 4


def test_transition_needs_a_full_sustained_window() -> None:
    conditions = run([0.8, 0.8, 0.8])

    assert conditions == [NORMAL, NORMAL, ALERT]


def test_no_transition_before_enough_history_exists() -> None:
    assert run([0.99, 0.99]) == [NORMAL, NORMAL]


# ─── Escalation ───────────────────────────────────────────────────────────


def test_sustained_mid_scores_reach_watch() -> None:
    assert run([0.55] * 3)[-1] is WATCH


def test_a_fast_degrading_unit_may_jump_straight_to_alert() -> None:
    # Escalation is deliberately allowed to skip WATCH; being late to raise an
    # alarm is the failure this system exists to prevent.
    assert run([0.9] * 3)[-1] is ALERT


def test_watch_escalates_to_alert() -> None:
    assert run([0.55] * 3 + [0.8] * 3)[-1] is ALERT


# ─── Hysteresis ───────────────────────────────────────────────────────────


def test_alert_holds_inside_the_deadband() -> None:
    # 0.70 is below the 0.75 entry threshold but above the 0.65 exit threshold.
    # Without hysteresis this would stand the alarm down.
    assert run([0.70] * 5, start=ALERT) == [ALERT] * 5


def test_watch_holds_inside_its_deadband() -> None:
    assert run([0.45] * 5, start=WATCH) == [WATCH] * 5


def test_alert_stands_down_only_as_far_as_watch() -> None:
    # De-escalation is stepwise even when the score collapses to zero.
    assert run([0.0] * 3, start=ALERT)[-1] is WATCH


def test_a_sustained_recovery_reaches_normal() -> None:
    assert run([0.0] * 6, start=ALERT)[-1] is NORMAL


def test_recovery_needs_the_full_window_too() -> None:
    assert run([0.0, 0.0], start=WATCH) == [WATCH, WATCH]


# ─── The behaviour all of the above exists to produce ──────────────────────


def test_a_score_oscillating_across_a_threshold_does_not_flap() -> None:
    # Alternating either side of watch_enter for twenty samples. With a bare
    # threshold this is twenty transitions; the deadband makes it zero.
    oscillation = [0.52, 0.48] * 10

    conditions = run(oscillation)

    assert set(conditions) == {NORMAL}


def test_a_genuine_degradation_produces_exactly_one_transition_per_level() -> None:
    ramp = [0.1] * 3 + [0.55] * 3 + [0.8] * 3
    conditions = run(ramp)

    transitions = [(before, after) for before, after in pairwise(conditions) if before is not after]

    assert transitions == [(NORMAL, WATCH), (WATCH, ALERT)]


def test_recorded_history_is_bounded() -> None:
    state = ConditionState()
    for score in [0.5] * 50:
        state = state.with_score(score, keep=20)

    assert len(state.recent_scores) == 20
