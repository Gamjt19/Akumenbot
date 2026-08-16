import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.models import Base, DailyReportHistory, Streak, Student, Submission
from bot.tasks import build_daily_report_text, get_target_report_date


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()

    # Patch get_session in bot.tasks to return this test session
    from contextlib import contextmanager

    @contextmanager
    def mock_get_session():
        yield session

    monkeypatch.setattr("bot.tasks.get_session", mock_get_session)

    try:
        yield session
    finally:
        session.close()


def test_target_report_date_at_00_05():
    """At 00:05 on Aug 16 in Asia/Kolkata, target report date is Aug 15."""
    kolkata_tz = ZoneInfo("Asia/Kolkata")
    now_kolkata = dt.datetime(2026, 8, 16, 0, 5, tzinfo=kolkata_tz)

    target_date = get_target_report_date(now_kolkata)
    assert target_date == dt.date(2026, 8, 15)


def test_timezone_handling_utc_vs_kolkata():
    """Verify UTC vs Asia/Kolkata timezone boundary handling."""
    # 2026-08-15 18:35 UTC is 2026-08-16 00:05 Asia/Kolkata
    utc_time = dt.datetime(2026, 8, 15, 18, 35, tzinfo=dt.timezone.utc)
    kolkata_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))

    assert kolkata_time.date() == dt.date(2026, 8, 16)
    target_date = get_target_report_date(kolkata_time)
    assert target_date == dt.date(2026, 8, 15)


def test_previous_day_report_calculation(db_session):
    """
    Ensure the report summarizes submissions from the target previous day
    and ignores submissions made on the current/next day.
    """
    target_date = dt.date(2026, 8, 15)
    next_date = dt.date(2026, 8, 16)

    # Student 1: submitted on target date (Aug 15)
    s1 = Student(discord_user_id="111", username="Rahul", active=True)
    db_session.add(s1)
    db_session.flush()
    db_session.add(Streak(student_id=s1.id, current_streak=31, best_streak=31, last_submission_date=target_date))
    db_session.add(
        Submission(
            student_id=s1.id,
            challenge_day=31,
            submission_date=target_date,
            message_id="msg_1",
            message_content="Day 31: finished project",
            is_valid=True,
        )
    )

    # Student 2: submitted on Aug 16 (NOT Aug 15)
    s2 = Student(discord_user_id="222", username="Gamil", active=True)
    db_session.add(s2)
    db_session.flush()
    db_session.add(Streak(student_id=s2.id, current_streak=24, best_streak=24, last_submission_date=next_date))
    db_session.add(
        Submission(
            student_id=s2.id,
            challenge_day=24,
            submission_date=next_date,
            message_id="msg_2",
            message_content="Day 24: project done",
            is_valid=True,
        )
    )

    # Student 3: did not submit
    s3 = Student(discord_user_id="333", username="Vishnu", active=True)
    db_session.add(s3)
    db_session.flush()
    db_session.add(Streak(student_id=s3.id, current_streak=5, best_streak=5, last_submission_date=dt.date(2026, 8, 10)))

    db_session.commit()

    report = build_daily_report_text(target_date)
    assert report is not None
    assert "Date: 15 August 2026" in report
    assert "Total Students: 3" in report
    assert "Submitted: 1" in report
    assert "Missing: 2" in report
    assert "@Rahul — Day 31 — 🔥 31" in report
    assert "@Gamil" in report  # Gamil is listed in NOT SUBMITTED for Aug 15
    assert "@Vishnu" in report


def test_duplicate_daily_report_prevention(db_session):
    """Verify DailyReportHistory records prevent duplicates."""
    target_date = dt.date(2026, 8, 15)

    # Initially not recorded
    existing = db_session.query(DailyReportHistory).filter_by(report_date=target_date).first()
    assert existing is None

    # Record delivery
    record = DailyReportHistory(
        report_date=target_date,
        sent_at=dt.datetime.now(dt.timezone.utc),
        channel_id="99999",
    )
    db_session.add(record)
    db_session.commit()

    # Now found in history
    existing = db_session.query(DailyReportHistory).filter_by(report_date=target_date).first()
    assert existing is not None
    assert existing.channel_id == "99999"
