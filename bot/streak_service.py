"""
Streak calculation logic.

This module is deliberately decoupled from Discord and from the database
session lifecycle where possible — the core function `compute_next_streak`
is pure (no I/O), so it can be unit tested without a bot, a database, or
a network connection.

Rules (from spec):
- First submission ever -> current streak = 1.
- Previous submission was exactly yesterday -> current streak += 1.
- Previous submission was more than 1 day ago (a day was missed) -> current streak = 1.
- A submission for "today" when today == last_submission_date is a duplicate
  and must not change the streak at all (handled by the caller before this
  function is invoked — see submission_service.record_submission).
- best_streak = max(best_streak, new current_streak).
- Calculation is based on calendar dates only, never on the student's
  self-reported "Day XX" text.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class StreakState:
    current_streak: int
    best_streak: int
    last_submission_date: dt.date | None


@dataclass(frozen=True)
class StreakResult:
    current_streak: int
    best_streak: int
    last_submission_date: dt.date
    streak_continued: bool  # True if this extended an existing streak
    streak_broken: bool  # True if a gap caused a reset to 1


def compute_next_streak(state: StreakState, submission_date: dt.date) -> StreakResult:
    """
    Given the student's current streak state and a NEW submission date,
    compute the resulting streak state.

    Caller is responsible for ensuring `submission_date` is not a duplicate
    of `state.last_submission_date` — this function assumes it is a genuine
    new calendar day being recorded.
    """
    if state.last_submission_date is None:
        # First submission ever.
        new_current = 1
        continued = False
        broken = False
    else:
        gap_days = (submission_date - state.last_submission_date).days

        if gap_days <= 0:
            # Same day or a submission dated before the last one (shouldn't
            # normally happen, but guard defensively rather than corrupt state).
            raise ValueError(
                f"submission_date {submission_date} is not after last_submission_date "
                f"{state.last_submission_date}; duplicates must be filtered before calling this."
            )
        elif gap_days == 1:
            new_current = state.current_streak + 1
            continued = True
            broken = False
        else:
            # One or more days were missed.
            new_current = 1
            continued = False
            broken = True

    new_best = max(state.best_streak, new_current)

    return StreakResult(
        current_streak=new_current,
        best_streak=new_best,
        last_submission_date=submission_date,
        streak_continued=continued,
        streak_broken=broken,
    )
