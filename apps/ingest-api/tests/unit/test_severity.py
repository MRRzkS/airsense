"""Rule 3 — severity mapping and escalation."""

import pytest

from airsense.domain.severity import Severity, SeverityPolicy, rate_of_change, worst

POLICY = SeverityPolicy(
    medium_band=0.60,
    high_band=0.75,
    critical_band=0.90,
    fast_degradation_per_sample=0.01,
)

LOW, MEDIUM, HIGH, CRITICAL = Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL


def flat(score: float, samples: int = 10) -> list[float]:
    return [score] * samples


def rising(end: float, per_sample: float, samples: int = 10) -> list[float]:
    return [end - per_sample * (samples - 1 - i) for i in range(samples)]


# ─── Bands ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, LOW),
        (0.59, LOW),
        (0.60, MEDIUM),
        (0.74, MEDIUM),
        (0.75, HIGH),
        (0.89, HIGH),
        (0.90, CRITICAL),
        (1.0, CRITICAL),
    ],
)
def test_a_stable_score_maps_to_its_band(score: float, expected: Severity) -> None:
    assert POLICY.evaluate(score, flat(score)) is expected


def test_bands_must_increase() -> None:
    with pytest.raises(ValueError, match="severity bands must increase"):
        SeverityPolicy(
            medium_band=0.8, high_band=0.7, critical_band=0.9, fast_degradation_per_sample=0.01
        )


def test_the_promotion_slope_must_be_positive() -> None:
    # Zero would promote every device, including perfectly stable ones.
    with pytest.raises(ValueError, match="must be positive"):
        SeverityPolicy(
            medium_band=0.6, high_band=0.75, critical_band=0.9, fast_degradation_per_sample=0.0
        )


# ─── Rate of change ───────────────────────────────────────────────────────


def test_a_single_sample_has_no_trend() -> None:
    # One reading is a position, not a trend. Inventing a slope from it would
    # let a spike promote a device.
    assert rate_of_change([0.9]) == 0.0
    assert rate_of_change([]) == 0.0


def test_rate_is_per_sample_not_per_window() -> None:
    assert rate_of_change([0.0, 0.1, 0.2, 0.3]) == pytest.approx(0.1)


def test_a_recovering_device_has_a_negative_rate() -> None:
    assert rate_of_change([0.8, 0.4]) < 0


# ─── Promotion ────────────────────────────────────────────────────────────


def test_a_fast_climbing_device_is_promoted_one_level() -> None:
    # Same score, different trajectory: the one that got here quickly is worse.
    stable = POLICY.evaluate(0.62, flat(0.62))
    climbing = POLICY.evaluate(0.62, rising(0.62, per_sample=0.02))

    assert stable is MEDIUM
    assert climbing is HIGH


def test_promotion_is_capped_at_critical() -> None:
    assert POLICY.evaluate(0.99, rising(0.99, per_sample=0.05)) is CRITICAL


def test_a_recovering_device_is_never_demoted() -> None:
    # Bad but improving is still bad. Only the band decides the floor.
    recovering = [0.95, 0.9, 0.85, 0.8]

    assert POLICY.evaluate(0.80, recovering) is HIGH


def test_a_slope_just_under_the_threshold_does_not_promote() -> None:
    assert POLICY.evaluate(0.62, rising(0.62, per_sample=0.009)) is MEDIUM


# ─── Ordering ─────────────────────────────────────────────────────────────


def test_severity_ranks_are_ordered() -> None:
    assert LOW.rank < MEDIUM.rank < HIGH.rank < CRITICAL.rank


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [(LOW, HIGH, HIGH), (HIGH, LOW, HIGH), (MEDIUM, MEDIUM, MEDIUM), (CRITICAL, HIGH, CRITICAL)],
)
def test_worst_returns_the_more_serious(
    left: Severity, right: Severity, expected: Severity
) -> None:
    assert worst(left, right) is expected
