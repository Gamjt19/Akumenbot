"""
Background tasks — daily summary report.

Runs at the configured time (default 00:05 Asia/Kolkata) to summarize the
PREVIOUS calendar day. Uses the database directly without unnecessary Discord
API scans and avoids duplicate execution on reconnects/restarts.
"""

from __future__ import annotations

import datetime as dt
import logging

import discord
from discord.ext import tasks
from zoneinfo import ZoneInfo

from bot.config import config
from bot.database import get_session
from bot.models import DailyReportHistory, Streak, Student, Submission

logger = logging.getLogger(__name__)

_report_task_instance: tasks.Loop | None = None


def get_target_report_date(now_local: dt.datetime | None = None) -> dt.date:
    """
    Computes the target report date.

    When running at 00:05 on August 16, the report summarizes the PREVIOUS
    calendar day (August 15).
    """
    if now_local is None:
        now_local = dt.datetime.now(ZoneInfo(config.timezone))
    return (now_local - dt.timedelta(days=1)).date()


def build_daily_report_text(target_date: dt.date | None = None) -> str | None:
    """
    Returns the formatted report string for target_date (defaults to previous calendar day),
    or None if there are no active students.
    """
    if target_date is None:
        target_date = get_target_report_date()

    with get_session() as session:
        active_students = (
            session.query(Student)
            .filter(Student.active.is_(True))
            .order_by(Student.username)
            .all()
        )
        if not active_students:
            return None

        # Fetch all valid submissions for target_date
        submissions = (
            session.query(Submission)
            .filter(Submission.submission_date == target_date, Submission.is_valid.is_(True))
            .all()
        )
        submission_by_student_id = {sub.student_id: sub for sub in submissions}

        # Fetch streak info for active students
        streaks = (
            session.query(Streak)
            .join(Student, Student.id == Streak.student_id)
            .filter(Student.active.is_(True))
            .all()
        )
        streak_by_student_id = {st.student_id: st for st in streaks}

        submitted_students = [s for s in active_students if s.id in submission_by_student_id]
        missing_students = [s for s in active_students if s.id not in submission_by_student_id]

        total_count = len(active_students)
        submitted_count = len(submitted_students)
        missing_count = len(missing_students)
        completion_pct = (submitted_count / total_count * 100) if total_count > 0 else 0.0

        # Determine top streaks
        active_student_streaks = [
            (s, streak_by_student_id.get(s.id))
            for s in active_students
            if streak_by_student_id.get(s.id) and streak_by_student_id[s.id].current_streak > 0
        ]
        active_student_streaks.sort(
            key=lambda x: (x[1].current_streak if x[1] else 0, x[1].best_streak if x[1] else 0),
            reverse=True,
        )

        medals = ["🥇", "🥈", "🥉"]
        top_streaks_lines: list[str] = []
        for idx, (student, streak) in enumerate(active_student_streaks[:3]):
            top_streaks_lines.append(f"{medals[idx]} @{student.username} — {streak.current_streak} days")

        lines: list[str] = [
            "📊 **DAILY CHALLENGE REPORT**",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"📅 Date: {target_date.strftime('%d %B %Y')}",
            "",
            f"👥 Total Students: {total_count}",
            f"✅ Submitted: {submitted_count}",
            f"❌ Missing: {missing_count}",
            f"📈 Completion: {completion_pct:.1f}%",
        ]

        if top_streaks_lines:
            lines.append("")
            lines.append("🔥 **TOP STREAKS**")
            lines.append("")
            lines.extend(top_streaks_lines)

        if submitted_students:
            lines.append("")
            lines.append("✅ **SUBMITTED**")
            lines.append("")
            for s in submitted_students:
                sub = submission_by_student_id[s.id]
                streak = streak_by_student_id.get(s.id)
                current_streak = streak.current_streak if streak else 0
                lines.append(f"@{s.username} — Day {sub.challenge_day} — 🔥 {current_streak}")

        if missing_students:
            lines.append("")
            lines.append("❌ **NOT SUBMITTED**")
            lines.append("")
            for s in missing_students:
                lines.append(f"@{s.username}")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)


async def send_chunked_report(channel: discord.abc.Messageable, text: str) -> None:
    """Sends text in chunks if it exceeds the 2000 character limit."""
    if len(text) <= 2000:
        await channel.send(text)
        return

    # Split lines safely
    lines = text.split("\n")
    current_chunk: list[str] = []
    current_length = 0

    for line in lines:
        if current_length + len(line) + 1 > 1950 and current_chunk:
            await channel.send("\n".join(current_chunk))
            current_chunk = []
            current_length = 0

        current_chunk.append(line)
        current_length += len(line) + 1

    if current_chunk:
        await channel.send("\n".join(current_chunk))


def setup_daily_report_task(bot: discord.Client) -> tasks.Loop:
    global _report_task_instance
    if _report_task_instance is not None and _report_task_instance.is_running():
        logger.info("Daily report task already running — skipping redundant startup.")
        return _report_task_instance

    report_time = dt.time(
        hour=config.daily_report_hour,
        minute=config.daily_report_minute,
        tzinfo=ZoneInfo(config.timezone),
    )

    @tasks.loop(time=report_time)
    async def daily_report():
        channel_id = config.trainer_channel_id or config.admin_channel_id
        if channel_id is None:
            logger.warning("TRAINER_CHANNEL_ID / ADMIN_CHANNEL_ID not set — skipping daily report.")
            return

        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception:
                logger.warning("Could not find trainer channel %s — skipping daily report.", channel_id)
                return

        target_date = get_target_report_date()

        # Check duplicate report prevention
        with get_session() as session:
            existing = (
                session.query(DailyReportHistory)
                .filter_by(report_date=target_date)
                .first()
            )
            if existing is not None:
                logger.info("Daily report for %s was already sent at %s — skipping duplicate.", target_date, existing.sent_at)
                return

        try:
            report = build_daily_report_text(target_date)
        except Exception:
            logger.exception("Failed to build daily report for %s", target_date)
            return

        if report is None:
            logger.info("No active students yet — skipping daily report for %s.", target_date)
            return

        try:
            await send_chunked_report(channel, report)
            # Record report in database
            with get_session() as session:
                record = DailyReportHistory(
                    report_date=target_date,
                    sent_at=dt.datetime.now(dt.timezone.utc),
                    channel_id=str(channel_id),
                )
                session.add(record)
            logger.info("Daily report for %s sent successfully to channel %s.", target_date, channel_id)
        except discord.DiscordException:
            logger.exception("Failed to send daily report to channel %s", channel_id)

    @daily_report.before_loop
    async def before_daily_report():
        await bot.wait_until_ready()

    daily_report.start()
    _report_task_instance = daily_report
    return daily_report
