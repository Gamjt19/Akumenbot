import datetime as dt
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.commands import check_user_is_trainer
from bot.models import Base, Streak, Student, Submission


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


def test_today_status_when_submitted(db_session):
    today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
    student = Student(discord_user_id="user_today_1", username="SubmittedToday", active=True)
    db_session.add(student)
    db_session.flush()

    sub = Submission(
        student_id=student.id,
        challenge_day=24,
        submission_date=today,
        message_id="msg_today",
        message_content="Day 24: complete",
        created_at=dt.datetime.now(dt.timezone.utc),
        is_valid=True,
    )
    streak = Streak(student_id=student.id, current_streak=24, best_streak=24, last_submission_date=today)
    db_session.add(sub)
    db_session.add(streak)
    db_session.commit()

    # Query today's status
    found_sub = (
        db_session.query(Submission)
        .filter_by(student_id=student.id, submission_date=today, is_valid=True)
        .first()
    )
    assert found_sub is not None
    assert found_sub.challenge_day == 24


def test_today_status_when_not_submitted(db_session):
    today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
    yesterday = today - dt.timedelta(days=1)

    student = Student(discord_user_id="user_today_2", username="NotSubmittedToday", active=True)
    db_session.add(student)
    db_session.flush()

    streak = Streak(student_id=student.id, current_streak=23, best_streak=23, last_submission_date=yesterday)
    db_session.add(streak)
    db_session.commit()

    found_sub = (
        db_session.query(Submission)
        .filter_by(student_id=student.id, submission_date=today, is_valid=True)
        .first()
    )
    assert found_sub is None
    found_streak = db_session.query(Streak).filter_by(student_id=student.id).first()
    assert found_streak.current_streak == 23


def test_leaderboard_ordering(db_session):
    s1 = Student(discord_user_id="1", username="Rahul", active=True)
    s2 = Student(discord_user_id="2", username="Gamil", active=True)
    s3 = Student(discord_user_id="3", username="Anu", active=True)
    s4 = Student(discord_user_id="4", username="TiedRahul", active=True)
    db_session.add_all([s1, s2, s3, s4])
    db_session.flush()

    # s1: current=31, best=31
    # s2: current=24, best=24
    # s3: current=19, best=19
    # s4: current=31, best=35 (should rank higher than s1 on tiebreak if best_streak is secondary sort)
    db_session.add(Streak(student_id=s1.id, current_streak=31, best_streak=31))
    db_session.add(Streak(student_id=s2.id, current_streak=24, best_streak=24))
    db_session.add(Streak(student_id=s3.id, current_streak=19, best_streak=19))
    db_session.add(Streak(student_id=s4.id, current_streak=31, best_streak=35))
    db_session.commit()

    ordered = (
        db_session.query(Student, Streak)
        .join(Streak, Streak.student_id == Student.id)
        .filter(Student.active.is_(True))
        .order_by(Streak.current_streak.desc(), Streak.best_streak.desc())
        .all()
    )

    names = [student.username for student, streak in ordered]
    assert names == ["TiedRahul", "Rahul", "Gamil", "Anu"]


def test_check_user_is_trainer():
    # 1. Admin user
    admin_user = MagicMock()
    admin_user.guild_permissions.administrator = True
    assert check_user_is_trainer(admin_user) is True

    # 2. User with trainer role
    trainer_role = MagicMock()
    trainer_role.name = "trainer"
    member_trainer = MagicMock()
    member_trainer.guild_permissions.administrator = False
    member_trainer.roles = [trainer_role]
    assert check_user_is_trainer(member_trainer) is True

    # 3. User with uppercase Trainer role
    trainer_role_upper = MagicMock()
    trainer_role_upper.name = "Trainer"
    member_trainer_upper = MagicMock()
    member_trainer_upper.guild_permissions.administrator = False
    member_trainer_upper.roles = [trainer_role_upper]
    assert check_user_is_trainer(member_trainer_upper) is True

    # 4. Regular student
    student_role = MagicMock()
    student_role.name = "student"
    member_student = MagicMock()
    member_student.guild_permissions.administrator = False
    member_student.roles = [student_role]
    assert check_user_is_trainer(member_student) is False
