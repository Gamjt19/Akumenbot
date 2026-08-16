import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.achievement_service import check_and_award_achievements
from bot.models import Achievement, Base, Student
from bot.submission_service import SubmissionOutcome, process_message


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_first_challenge_achievement(db_session):
    student = Student(discord_user_id="user_first", username="NewUser")
    db_session.add(student)
    db_session.flush()

    new_badges = check_and_award_achievements(
        db_session,
        student_id=student.id,
        current_streak=1,
        total_submissions=1,
    )
    db_session.commit()

    assert "First Challenge" in new_badges
    saved_achievements = db_session.query(Achievement).filter_by(student_id=student.id).all()
    assert len(saved_achievements) == 1
    assert saved_achievements[0].badge_name == "First Challenge"


def test_achievement_awarded_only_once(db_session):
    student = Student(discord_user_id="user_idempotent", username="TestUser")
    db_session.add(student)
    db_session.flush()

    # First check awards First Challenge
    badges_1 = check_and_award_achievements(
        db_session,
        student_id=student.id,
        current_streak=1,
        total_submissions=1,
    )
    db_session.commit()
    assert "First Challenge" in badges_1

    # Second check with same stats must return empty list (no duplicate badge)
    badges_2 = check_and_award_achievements(
        db_session,
        student_id=student.id,
        current_streak=1,
        total_submissions=1,
    )
    db_session.commit()
    assert len(badges_2) == 0

    all_badges = db_session.query(Achievement).filter_by(student_id=student.id).all()
    assert len(all_badges) == 1


def test_7_day_and_14_day_streak_achievements(db_session):
    student = Student(discord_user_id="user_streak7", username="StreakStudent")
    db_session.add(student)
    db_session.flush()

    # Pre-award first challenge
    check_and_award_achievements(db_session, student.id, current_streak=1, total_submissions=1)
    db_session.commit()

    # Reach 7 day streak
    badges_at_7 = check_and_award_achievements(
        db_session,
        student_id=student.id,
        current_streak=7,
        total_submissions=7,
    )
    db_session.commit()
    assert "7 Day Streak" in badges_at_7
    assert "14 Day Streak" not in badges_at_7

    # Reach 14 day streak and 10 submissions
    badges_at_14 = check_and_award_achievements(
        db_session,
        student_id=student.id,
        current_streak=14,
        total_submissions=14,
    )
    db_session.commit()
    assert "14 Day Streak" in badges_at_14
    assert "10 Submissions" in badges_at_14


def test_30_day_streak_achievement(db_session):
    student = Student(discord_user_id="user_streak30", username="LongStreakStudent")
    db_session.add(student)
    db_session.flush()

    badges = check_and_award_achievements(
        db_session,
        student_id=student.id,
        current_streak=30,
        total_submissions=30,
    )
    db_session.commit()
    assert "30 Day Streak" in badges
    assert "25 Submissions" in badges


def test_achievement_integrated_in_process_message(db_session):
    now = dt.datetime(2026, 8, 15, 10, 0, tzinfo=dt.timezone.utc)
    res = process_message(
        db_session,
        discord_user_id="user_msg_test",
        username="IntegrationUser",
        message_id="msg_int_1",
        message_content="Day 1: hello",
        message_timestamp_utc=now,
        timezone_name="Asia/Kolkata",
    )
    assert res.outcome == SubmissionOutcome.RECORDED
    assert "First Challenge" in res.new_achievements
