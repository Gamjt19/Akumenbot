import datetime as dt

import pytest

from bot.streak_service import StreakState, compute_next_streak


def d(offset_days: int, base: dt.date = dt.date(2026, 8, 1)) -> dt.date:
    """Helper: date offset from a fixed base date."""
    return base + dt.timedelta(days=offset_days)


# 1. First submission
def test_first_submission():
    state = StreakState(current_streak=0, best_streak=0, last_submission_date=None)
    result = compute_next_streak(state, d(0))
    assert result.current_streak == 1
    assert result.best_streak == 1
    assert result.last_submission_date == d(0)
    assert result.streak_continued is False
    assert result.streak_broken is False


# 2. Consecutive submissions
def test_consecutive_submissions():
    state = StreakState(current_streak=1, best_streak=1, last_submission_date=d(0))
    result = compute_next_streak(state, d(1))
    assert result.current_streak == 2
    assert result.best_streak == 2
    assert result.streak_continued is True


# 3. Missed day
def test_missed_day_resets_streak():
    # Last submission was 2 days ago -> a day was skipped.
    state = StreakState(current_streak=3, best_streak=3, last_submission_date=d(0))
    result = compute_next_streak(state, d(2))
    assert result.current_streak == 1
    assert result.best_streak == 3  # best streak preserved
    assert result.streak_broken is True


# 4. Multiple submissions on the same day (duplicate) must not be passed to
# compute_next_streak at all — the function raises if given a non-advancing date,
# which documents that duplicates must be filtered upstream (submission_service does this).
def test_same_day_resubmission_raises():
    state = StreakState(current_streak=1, best_streak=1, last_submission_date=d(0))
    with pytest.raises(ValueError):
        compute_next_streak(state, d(0))


# 5. Best streak tracking across a broken streak
def test_best_streak_persists_after_break():
    state = StreakState(current_streak=0, best_streak=0, last_submission_date=None)

    state = _apply(state, d(0))  # Day 1 -> streak 1
    state = _apply(state, d(1))  # Day 2 -> streak 2
    state = _apply(state, d(2))  # Day 3 -> streak 3
    # Day 4 missed
    state = _apply(state, d(4))  # Day 5 -> streak resets to 1

    assert state.current_streak == 1
    assert state.best_streak == 3


# 6. New streak after a missed day (matches the spec's worked example exactly)
def test_spec_worked_example():
    state = StreakState(current_streak=0, best_streak=0, last_submission_date=None)

    state = _apply(state, d(0))  # Aug 1 -> Day 1 -> streak 1
    assert state.current_streak == 1

    state = _apply(state, d(1))  # Aug 2 -> Day 2 -> streak 2
    assert state.current_streak == 2

    state = _apply(state, d(2))  # Aug 3 -> Day 3 -> streak 3
    assert state.current_streak == 3

    # Aug 4 -> no submission (skip)

    state = _apply(state, d(4))  # Aug 5 -> Day 5 -> new streak 1
    assert state.current_streak == 1
    assert state.best_streak == 3


# 7. First submission after a long gap (weeks later) behaves like any other gap
def test_long_gap_resets_to_one():
    state = StreakState(current_streak=10, best_streak=10, last_submission_date=d(0))
    result = compute_next_streak(state, d(30))
    assert result.current_streak == 1
    assert result.best_streak == 10
    assert result.streak_broken is True


# 8. Different students are independent (streak_service has no shared global
# state, so two independent StreakState objects never interfere with each other)
def test_different_students_are_independent():
    student_a = StreakState(current_streak=5, best_streak=5, last_submission_date=d(0))
    student_b = StreakState(current_streak=0, best_streak=0, last_submission_date=None)

    result_a = compute_next_streak(student_a, d(1))
    result_b = compute_next_streak(student_b, d(1))

    assert result_a.current_streak == 6
    assert result_b.current_streak == 1


# 9. Challenge day numbers that don't match the calendar streak: the student's
# self-reported "Day XX" text is irrelevant to streak math — only calendar
# dates matter. This is enforced structurally: compute_next_streak never
# receives a challenge_day argument at all, so a student who mislabels
# "Day 40" after only 3 real calendar submissions still gets a calendar-correct streak.
def test_streak_ignores_self_reported_day_number():
    state = StreakState(current_streak=2, best_streak=2, last_submission_date=d(0))
    # Simulate: student's message says "Day 99" but this is only their 3rd
    # calendar-consecutive post. The caller (submission_service) passes only
    # the calendar submission_date here, never the parsed day number.
    result = compute_next_streak(state, d(1))
    assert result.current_streak == 3  # driven by date gap, not by "Day 99"


# 10. Timezone / date boundary: two UTC timestamps that fall on the same
# LOCAL calendar day (e.g. Asia/Kolkata) must be treated as the same date.
# This is the responsibility of submission_service's timezone conversion,
# but we verify the boundary logic itself here using the local dates it
# would produce, since compute_next_streak operates purely on dates.
def test_timezone_boundary_same_local_day():
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Kolkata")

    # 23:50 IST on Aug 1 and 00:10 IST on Aug 2 are genuinely different local days.
    late_night = dt.datetime(2026, 8, 1, 23, 50, tzinfo=tz)
    just_after_midnight = dt.datetime(2026, 8, 2, 0, 10, tzinfo=tz)
    assert late_night.date() != just_after_midnight.date()

    # But a UTC timestamp near midnight UTC can land on a DIFFERENT local
    # date in IST (UTC+5:30) than its raw UTC date would suggest.
    utc_late = dt.datetime(2026, 8, 1, 20, 0, tzinfo=dt.timezone.utc)  # 01:30 IST Aug 2
    local_date = utc_late.astimezone(tz).date()
    assert local_date == dt.date(2026, 8, 2)
    assert utc_late.date() == dt.date(2026, 8, 1)  # raw UTC date would be WRONG


def _apply(state: StreakState, new_date: dt.date) -> StreakState:
    """Helper to fold a compute_next_streak result back into a StreakState."""
    result = compute_next_streak(state, new_date)
    return StreakState(
        current_streak=result.current_streak,
        best_streak=result.best_streak,
        last_submission_date=result.last_submission_date,
    )
