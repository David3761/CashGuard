"""The shared hypothesis profile is active for every test (determinism rule, how-we-work §7)."""

from hypothesis import settings


def test_hypothesis_profile_is_deterministic_and_has_no_deadline() -> None:
    active = settings()

    assert active.derandomize is True
    assert active.deadline is None
