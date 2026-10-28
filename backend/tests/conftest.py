"""Shared test config. bomboe's F3 adds the db / api / auth / ws fixtures here (HANDOFFS H-4)."""

from hypothesis import settings

# Determinism (how-we-work §7): the same examples on every run and machine, so a failure is
# reproducible. No deadline: parallel agents and CI load make timing-based failures flaky.
settings.register_profile("cashguard", derandomize=True, deadline=None, print_blob=True)
settings.load_profile("cashguard")
