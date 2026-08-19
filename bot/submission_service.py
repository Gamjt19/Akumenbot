"""
Ties together: parsed message -> student record -> submission row -> streak update.

This is the layer main.py's on_message handler calls into. Keeping it out of
main.py means the "what happens when a valid message arrives" logic can be
reasoned about (and tested) without spinning up a real Discord connection.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from enum import Enum, auto

from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from bot.achievement_service import check_and_award_achievements
from bot.models import Streak, Student, Submission
from bot.parser import parse_submission
from bot.streak_service import StreakState, compute_next_streak

logger = logging.getLogger(__name__)


class SubmissionOutcome(Enum):
    NOT_A_SUBMISSION = auto()      # message didn't match "Day N" pattern
    RECORDED = auto()              # new valid submission, streak updated
    DUPLICATE_SAME_DAY = auto()    # student already has an official submission today
    INVALID_DAY_NUMBER = auto()    # student typed day number != expected day number
    STREAK_BROKEN_MUST_RESTART = auto()  # student missed a day and must restart from Day 1


@dataclass(frozen=True)
class SubmissionResult:
    outcome: SubmissionOutcome
    challenge_day: int | None = None
    expected_day: int | None = None
    current_streak: int | None = None
    best_streak: int | None = None
    streak_broken: bool = False
    last_valid_day: int | None = None  # the last day the student successfully submitted
    new_achievements: tuple[str, ...] = ()


def get_or_create_student(session: Session, discord_user_id: str, username: str) -> Student:
    student = session.query(Student).filter_by(discord_user_id=discord_user_id).one_or_none()
    if student is None:
        student = Student(discord_user_id=discord_user_id, username=username)
        session.add(student)
        session.flush()  # get student.id without a full commit
        session.add(Streak(student_id=student.id, current_streak=0, best_streak=0))
        session.flush()
    else:
        # Keep the display name reasonably fresh (Discord usernames can change).
        if student.username != username:
            student.username = username
        # Ensure streak row exists even if it was manually deleted from database
        streak = session.query(Streak).filter_by(student_id=student.id).one_or_none()
        if streak is None:
            session.add(Streak(student_id=student.id, current_streak=0, best_streak=0))
            session.flush()
    return student


def process_message(
    session: Session,
    *,
    discord_user_id: str,
    username: str,
    message_id: str,
    message_content: str,
    message_timestamp_utc: dt.datetime,
    timezone_name: str,
) -> SubmissionResult:
    """
    Core entry point called from the on_message handler.

    - Parses the message.
    - If not a valid "Day N" post -> NOT_A_SUBMISSION.
    - Converts the message's UTC timestamp to the configured local timezone
      to determine the calendar submission_date (never trusts the day number
      the student typed for date purposes).
    - If the student already has an official submission for that local date
      -> DUPLICATE_SAME_DAY (stored as a non-counting row).
      - Otherwise -> records the submission and updates the streak.
    """
    parsed = parse_submission(message_content)
    if parsed is None:
        return SubmissionResult(outcome=SubmissionOutcome.NOT_A_SUBMISSION)

    local_tz = ZoneInfo(timezone_name)
    submission_date = message_timestamp_utc.astimezone(local_tz).date()

    student = get_or_create_student(session, discord_user_id, username)

    existing_official = (
        session.query(Submission)
        .filter_by(student_id=student.id, submission_date=submission_date, is_valid=True)
        .one_or_none()
    )

    if existing_official is not None:
        # Check if a duplicate record with is_valid=False already exists for today
        # to avoid violating uq_student_date_valid if the student posts 3+ times.
        existing_duplicate = (
            session.query(Submission)
            .filter_by(student_id=student.id, submission_date=submission_date, is_valid=False)
            .first()
        )
        if existing_duplicate is None:
            try:
                duplicate = Submission(
                    student_id=student.id,
                    challenge_day=parsed.challenge_day,
                    submission_date=submission_date,
                    message_id=message_id,
                    message_content=message_content,
                    is_valid=False,
                )
                session.add(duplicate)
                session.flush()
            except Exception:
                session.rollback()
        return SubmissionResult(outcome=SubmissionOutcome.DUPLICATE_SAME_DAY)

    last_sub = (
        session.query(Submission)
        .filter_by(student_id=student.id, is_valid=True)
        .order_by(Submission.id.desc())
        .first()
    )

    # Determine whether the student missed one or more calendar days.
    # If they did, the streak resets and they MUST restart from Day 1,
    # regardless of what day number they typed.
    streak_was_broken = False
    if last_sub is not None:
        gap_days = (submission_date - last_sub.submission_date).days
        if gap_days > 1:
            streak_was_broken = True

    if streak_was_broken:
        # Student missed a day — day counter must restart from 1.
        if parsed.challenge_day != 1:
            return SubmissionResult(
                outcome=SubmissionOutcome.STREAK_BROKEN_MUST_RESTART,
                challenge_day=parsed.challenge_day,
                expected_day=1,
                last_valid_day=last_sub.challenge_day if last_sub else None,
            )
        # They correctly posted Day 1; fall through to record it.
        expected_day = 1
    else:
        expected_day = (last_sub.challenge_day + 1) if last_sub is not None else 1

    if parsed.challenge_day != expected_day:
        return SubmissionResult(
            outcome=SubmissionOutcome.INVALID_DAY_NUMBER,
            challenge_day=parsed.challenge_day,
            expected_day=expected_day,
        )

    streak_row = session.query(Streak).filter_by(student_id=student.id).one()
    prior_state = StreakState(
        current_streak=streak_row.current_streak if last_sub is not None else 0,
        best_streak=streak_row.best_streak,
        last_submission_date=last_sub.submission_date if last_sub is not None else None,
    )

    result = compute_next_streak(prior_state, submission_date)

    submission = Submission(
        student_id=student.id,
        challenge_day=parsed.challenge_day,
        submission_date=submission_date,
        message_id=message_id,
        message_content=message_content,
        is_valid=True,
    )
    session.add(submission)

    streak_row.current_streak = result.current_streak
    streak_row.best_streak = result.best_streak
    streak_row.last_submission_date = result.last_submission_date
    session.flush()

    total_valid_submissions = (
        session.query(Submission)
        .filter_by(student_id=student.id, is_valid=True)
        .count()
    )
    new_badges = check_and_award_achievements(
        session,
        student_id=student.id,
        current_streak=result.current_streak,
        total_submissions=total_valid_submissions,
    )

    return SubmissionResult(
        outcome=SubmissionOutcome.RECORDED,
        challenge_day=parsed.challenge_day,
        current_streak=result.current_streak,
        best_streak=result.best_streak,
        streak_broken=result.streak_broken,
        new_achievements=tuple(new_badges),
    )
