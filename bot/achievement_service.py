"""
Achievement / Badge service.

Tracks milestones and awards badges to students for streak lengths and
total submission counts. Badges are persisted to the database and awarded
only once per student.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Callable, NamedTuple

from sqlalchemy.orm import Session

from bot.models import Achievement

logger = logging.getLogger(__name__)


class BadgeDefinition(NamedTuple):
    badge_key: str
    badge_name: str
    is_eligible: Callable[[int, int], bool]  # (current_streak, total_submissions) -> bool


BADGE_CATALOG: list[BadgeDefinition] = [
    BadgeDefinition("first_challenge", "First Challenge", lambda streak, total: total >= 1 or streak >= 1),
    BadgeDefinition("streak_7", "7 Day Streak", lambda streak, total: streak >= 7),
    BadgeDefinition("streak_14", "14 Day Streak", lambda streak, total: streak >= 14),
    BadgeDefinition("streak_30", "30 Day Streak", lambda streak, total: streak >= 30),
    BadgeDefinition("streak_50", "50 Day Streak", lambda streak, total: streak >= 50),
    BadgeDefinition("streak_100", "100 Day Streak", lambda streak, total: streak >= 100),
    BadgeDefinition("submissions_10", "10 Submissions", lambda streak, total: total >= 10),
    BadgeDefinition("submissions_25", "25 Submissions", lambda streak, total: total >= 25),
    BadgeDefinition("submissions_50", "50 Submissions", lambda streak, total: total >= 50),
    BadgeDefinition("submissions_100", "100 Submissions", lambda streak, total: total >= 100),
]


def check_and_award_achievements(
    session: Session,
    student_id: int,
    current_streak: int,
    total_submissions: int,
) -> list[str]:
    """
    Evaluates milestone criteria against a student's stats and records
    newly unlocked achievements in the database.

    Returns a list of badge names that were unlocked during this check.
    """
    existing_keys = {
        row.badge_key
        for row in session.query(Achievement.badge_key).filter_by(student_id=student_id).all()
    }

    newly_awarded: list[str] = []
    now = dt.datetime.now(dt.timezone.utc)

    for badge in BADGE_CATALOG:
        if badge.badge_key not in existing_keys and badge.is_eligible(current_streak, total_submissions):
            try:
                achievement = Achievement(
                    student_id=student_id,
                    badge_key=badge.badge_key,
                    badge_name=badge.badge_name,
                    earned_at=now,
                )
                session.add(achievement)
                session.flush()
                newly_awarded.append(badge.badge_name)
                logger.info("Student %s unlocked badge: %s", student_id, badge.badge_name)
            except Exception:
                session.rollback()
                logger.warning(
                    "Could not award badge %s to student %s (may have been awarded concurrently)",
                    badge.badge_key,
                    student_id,
                )

    return newly_awarded
