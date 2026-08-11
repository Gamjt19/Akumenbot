"""
Background tasks — currently just the once-a-day report.

Uses discord.ext.tasks with time_of_day scheduling in the configured
timezone. This task only READS from the database to build the report;
it never mutates streaks or submissions. Streak state is fully determined
by submission dates, not by when this task happens to run.
"""

from __future__ import annotations

import datetime as dt
import logging

import discord
from discord.ext import tasks
from zoneinfo import ZoneInfo

from bot.config import config
from bot.database import get_session
from bot.models import Student, Submission

logger = logging.getLogger(__name__)


def _today_local() -> dt.date:
    return dt.datetime.now(ZoneInfo(config.timezone)).date()


def build_daily_report_text() -> str | None:
    """Returns the formatted report string, or None if there are no active students."""
    with get_session() as session:
        today = _today_local()

        active_students = session.query(Student).filter(Student.active.is_(True)).all()
        if not active_students:
            return None

        submitted_ids = {
            row.student_id
            for row in session.query(Submission.student_id)
            .filter(Submission.submission_date == today, Submission.is_valid.is_(True))
            .all()
        }

        missing = [s for s in active_students if s.id not in submitted_ids]
        submitted_count = len(active_students) - len(missing)

        lines = [
            "📋 **Daily Challenge Report**",
            "",
            f"Date: {today.strftime('%d %B %Y')}",
            "",
            f"Students: {len(active_students)}",
            f"Submitted: {submitted_count} ✅",
            f"Missing: {len(missing)} ❌",
        ]

        if missing:
            lines.append("")
            lines.append("**Missing students:**")
            for student in missing:
                lines.append(f"* {student.username}")

        return "\n".join(lines)


def setup_daily_report_task(bot: discord.Client) -> None:
    report_time = dt.time(
        hour=config.daily_report_hour,
        minute=config.daily_report_minute,
        tzinfo=ZoneInfo(config.timezone),
    )

    @tasks.loop(time=report_time)
    async def daily_report():
        if config.admin_channel_id is None:
            logger.warning("ADMIN_CHANNEL_ID not set — skipping daily report.")
            return

        channel = bot.get_channel(config.admin_channel_id)
        if channel is None:
            logger.warning("Could not find admin channel %s — skipping daily report.", config.admin_channel_id)
            return

        try:
            report = build_daily_report_text()
        except Exception:
            logger.exception("Failed to build daily report")
            return

        if report is None:
            logger.info("No active students yet — skipping daily report.")
            return

        try:
            await channel.send(report)
        except discord.DiscordException:
            logger.exception("Failed to send daily report to channel %s", config.admin_channel_id)

    @daily_report.before_loop
    async def before_daily_report():
        await bot.wait_until_ready()

    daily_report.start()
    return daily_report
