import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.models import Base
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


def test_first_submission_invalid_day_rejected(db_session):
    now = dt.datetime(2026, 8, 12, 10, 0, tzinfo=dt.timezone.utc)
    result = process_message(
        db_session,
        discord_user_id="user_123",
        username="TestUser",
        message_id="msg_1",
        message_content="Day 65: hello",
        message_timestamp_utc=now,
        timezone_name="Asia/Kolkata",
    )
    assert result.outcome == SubmissionOutcome.INVALID_DAY_NUMBER
    assert result.challenge_day == 65
    assert result.expected_day == 1


def test_first_submission_valid_day_recorded(db_session):
    now = dt.datetime(2026, 8, 12, 10, 0, tzinfo=dt.timezone.utc)
    result = process_message(
        db_session,
        discord_user_id="user_123",
        username="TestUser",
        message_id="msg_1",
        message_content="Day 1: hello",
        message_timestamp_utc=now,
        timezone_name="Asia/Kolkata",
    )
    assert result.outcome == SubmissionOutcome.RECORDED
    assert result.challenge_day == 1
    assert result.current_streak == 1


def test_sequential_submission_validation(db_session):
    day1_time = dt.datetime(2026, 8, 12, 10, 0, tzinfo=dt.timezone.utc)
    # Day 1 recorded
    res1 = process_message(
        db_session,
        discord_user_id="user_123",
        username="TestUser",
        message_id="msg_1",
        message_content="Day 1: First day",
        message_timestamp_utc=day1_time,
        timezone_name="Asia/Kolkata",
    )
    assert res1.outcome == SubmissionOutcome.RECORDED

    # Day 2 on next calendar day: student tries typing Day 5
    day2_time = dt.datetime(2026, 8, 13, 10, 0, tzinfo=dt.timezone.utc)
    res2 = process_message(
        db_session,
        discord_user_id="user_123",
        username="TestUser",
        message_id="msg_2",
        message_content="Day 5: Wrong day",
        message_timestamp_utc=day2_time,
        timezone_name="Asia/Kolkata",
    )
    assert res2.outcome == SubmissionOutcome.INVALID_DAY_NUMBER
    assert res2.challenge_day == 5
    assert res2.expected_day == 2

    # Student retries with correct Day 2
    res3 = process_message(
        db_session,
        discord_user_id="user_123",
        username="TestUser",
        message_id="msg_3",
        message_content="Day 2: Correct day",
        message_timestamp_utc=day2_time,
        timezone_name="Asia/Kolkata",
    )
    assert res3.outcome == SubmissionOutcome.RECORDED
    assert res3.challenge_day == 2
    assert res3.current_streak == 2


def test_cleared_submissions_resets_streak_state(db_session):
    from bot.models import Streak, Student, Submission
    # Create student with streak.last_submission_date set to today, but no submissions
    now = dt.datetime(2026, 8, 12, 10, 0, tzinfo=dt.timezone.utc)
    student = Student(discord_user_id="user_out_of_sync", username="StaleUser")
    db_session.add(student)
    db_session.flush()
    streak = Streak(student_id=student.id, current_streak=1, best_streak=1, last_submission_date=now.date())
    db_session.add(streak)
    db_session.commit()

    # Now process message "Day 1: fresh start"
    res = process_message(
        db_session,
        discord_user_id="user_out_of_sync",
        username="StaleUser",
        message_id="msg_stale",
        message_content="Day 1: fresh start",
        message_timestamp_utc=now,
        timezone_name="Asia/Kolkata",
    )
    assert res.outcome == SubmissionOutcome.RECORDED
    assert res.challenge_day == 1
    assert res.current_streak == 1
