"""
SQLAlchemy ORM models for the challenge tracker.

Tables:
    students     - one row per Discord user who has ever submitted
    submissions  - one row per message that looked like a valid submission
    streaks      - one row per student, current/best streak state
    settings     - one row per guild, runtime-configurable settings
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    submissions: Mapped[list["Submission"]] = relationship(back_populates="student")
    streak: Mapped["Streak"] = relationship(back_populates="student", uselist=False)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        # Enforces: at most one OFFICIAL (is_valid=True, first-of-day) submission
        # per student per calendar date. We enforce "first valid per day" at the
        # application layer (see streak_service) and use this constraint as a
        # hard backstop against race conditions / duplicate official rows.
        UniqueConstraint("student_id", "submission_date", "is_valid", name="uq_student_date_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    challenge_day: Mapped[int] = mapped_column(Integer, nullable=False)
    submission_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    message_content: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, nullable=False)
    # is_valid=True means "this counted toward the streak" (first valid post of the day).
    # Later duplicate posts on the same day are stored with is_valid=False so the
    # unique constraint above only ever guards the one official row per day.
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    student: Mapped["Student"] = relationship(back_populates="submissions")


class Streak(Base):
    __tablename__ = "streaks"

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), primary_key=True)
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_submission_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    student: Mapped["Student"] = relationship(back_populates="streak")


class Settings(Base):
    __tablename__ = "settings"

    guild_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    submission_channel_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    admin_channel_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    challenge_started_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
