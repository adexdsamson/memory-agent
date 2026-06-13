"""Phase 2 decay / keep_score tests — FORG-01 and FORG-03 (partial).

All tests in this module are RED stubs for the walking-skeleton wave.  They test
``mnema.core.decay.keep_score``, a pure synchronous function that computes a
retention score for a MemoryRecord.

  FORG-01  keep_score returns a float in [0, 1] with the correct weighted formula
  FORG-03  (partial) the decay_pass caller must skip protected records before
           invoking keep_score -- the guard lives in the caller, not inside the
           pure scoring function

``keep_score`` is a D-12 sans-I/O function -- tests are plain ``def`` (no async
required) and need no engine fixture.  The deferred import style keeps the test
collectable before the implementation exists.
"""

from __future__ import annotations

from datetime import datetime, timezone


class TestDecay:
    def test_keep_score_values(self) -> None:
        """FORG-01: keep_score returns float in [0,1]; correct formula for known inputs."""
        from mnema.core.decay import keep_score  # noqa: PLC0415

        raise NotImplementedError("FORG-01 keep_score not implemented")

    def test_protected_skipped_before_score_math(self) -> None:
        """FORG-03 (partial): decay_pass must not yield protected records at all.

        This test verifies the guard lives in the caller, not inside keep_score itself.
        keep_score may be called on a protected record without raising -- the caller is
        responsible for skipping protected records before invoking it.
        """
        from mnema.core.decay import keep_score  # noqa: PLC0415

        raise NotImplementedError("keep_score guard test not implemented")
