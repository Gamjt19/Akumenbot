"""
Slash commands.

Student commands:  /assignment, /assignments, /mystats, /today, /leaderboard, /progress, /help, /ping
Trainer/admin-only: /status, /missed, /reset, /export

Permission model: trainer-only commands check for a configurable Discord
role (TRAINER_ROLE_NAME env var, default "trainer") OR server Administrator
permission. No individual Discord user IDs are ever hardcoded.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging

import discord
from discord import app_commands
from discord.ext import commands
from zoneinfo import ZoneInfo

from bot.config import config
from bot.database import get_session
from bot.models import Achievement, Assignment, Settings, Streak, Student, Submission

logger = logging.getLogger(__name__)


def check_user_is_trainer(user: discord.abc.User | discord.Member | None) -> bool:
    """Checks if a user is an administrator or has the configured trainer role."""
    if user is None:
        return False
    guild_perms = getattr(user, "guild_permissions", None)
    if guild_perms and guild_perms.administrator:
        return True
    roles = getattr(user, "roles", [])
    role_names = {role.name.lower() for role in roles}
    if config.trainer_role_name.lower() in role_names:
        return True
    return False


def is_trainer():
    """Check decorator: allows server admins or members with the trainer role."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if check_user_is_trainer(interaction.user):
            return True
        await interaction.response.send_message(
            f"🚫 This command is restricted to trainers (`{config.trainer_role_name}` role) or admins.",
            ephemeral=True,
        )
        return False

    return app_commands.check(predicate)


def _today_local() -> dt.date:
    return dt.datetime.now(ZoneInfo(config.timezone)).date()


def format_post_message(topic: str, details: str, author_id: str | int, posted_str: str) -> str:
    """Formats a post message in a neutral style without 'NEW ASSIGNMENT' heading."""
    return (
        f"📌 **{topic}**\n\n"
        f"{details}\n\n"
        f"👤 **Posted by:** <@{author_id}>\n"
        f"🕒 **Posted:** {posted_str}"
    )


class CreatePostModal(discord.ui.Modal, title="Create Post"):
    topic: discord.ui.TextInput = discord.ui.TextInput(
        label="Topic",
        style=discord.TextStyle.short,
        placeholder="e.g. Project 34, Docker Task, Homework...",
        required=True,
        max_length=256,
    )
    details: discord.ui.TextInput = discord.ui.TextInput(
        label="Details",
        style=discord.TextStyle.paragraph,
        placeholder="Enter details or instructions here...",
        required=True,
        max_length=2000,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        topic_val = self.topic.value.strip()
        details_val = self.details.value

        if not topic_val or not details_val.strip():
            await interaction.response.send_message(
                "❌ Topic and details cannot be empty.",
                ephemeral=True,
            )
            return

        channel_id = config.assignments_channel_id
        if channel_id is None:
            logger.warning("ASSIGNMENTS_CHANNEL_ID is not configured.")
            await interaction.response.send_message(
                "❌ I couldn't post right now. Please contact the developer.",
                ephemeral=True,
            )
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                logger.exception("Failed to fetch assignments channel %s: %s", channel_id, e)
                await interaction.response.send_message(
                    "❌ I couldn't post right now. Please contact the developer.",
                    ephemeral=True,
                )
                return

        now_local = dt.datetime.now(ZoneInfo(config.timezone))
        posted_str = now_local.strftime("%d %b %Y, %I:%M %p")

        post_msg = format_post_message(
            topic=topic_val,
            details=details_val,
            author_id=interaction.user.id,
            posted_str=posted_str,
        )

        try:
            sent_msg = await channel.send(post_msg)
        except Exception as e:
            logger.exception("Failed to send message to assignments channel %s: %s", channel_id, e)
            await interaction.response.send_message(
                "❌ I couldn't post right now. Please contact the developer.",
                ephemeral=True,
            )
            return

        try:
            with get_session() as session:
                record = Assignment(
                    author_discord_id=str(interaction.user.id),
                    author_username=interaction.user.display_name,
                    topic=topic_val,
                    details=details_val,
                    created_at=dt.datetime.now(dt.timezone.utc),
                    discord_message_id=str(sent_msg.id),
                    channel_id=str(channel_id),
                )
                session.add(record)
        except Exception as e:
            logger.exception("Failed to record assignment in database: %s", e)

        await interaction.response.send_message(
            f"✅ Post created successfully!\n\n📌 **{topic_val}**\n\nIt has been posted in <#{channel_id}>.",
            ephemeral=True,
        )


def setup_commands(bot: commands.Bot) -> None:
    tree = bot.tree

    @tree.command(name="ping", description="Check if the bot is online.")
    async def ping(interaction: discord.Interaction):
        await interaction.response.send_message("🏓 Pong! Bot is online.")

    @tree.command(name="assignment", description="Submit a new post or assignment to the assignments channel.")
    async def assignment(interaction: discord.Interaction):
        await interaction.response.send_modal(CreatePostModal(bot=bot))

    @tree.command(name="assignments", description="Show recent assignment posts.")
    async def assignments(interaction: discord.Interaction):
        with get_session() as session:
            rows = (
                session.query(Assignment)
                .order_by(Assignment.created_at.desc())
                .limit(10)
                .all()
            )

            if not rows:
                await interaction.response.send_message("📚 No assignments posted yet.")
                return

            number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            lines = ["📚 **RECENT ASSIGNMENTS**", ""]
            guild_id = interaction.guild_id or config.guild_id

            for idx, item in enumerate(rows):
                prefix = number_emojis[idx] if idx < len(number_emojis) else f"{idx + 1}."
                local_time = item.created_at.replace(tzinfo=dt.timezone.utc).astimezone(ZoneInfo(config.timezone))
                date_str = local_time.strftime("%d %b")

                link_str = ""
                if guild_id and item.channel_id and item.discord_message_id:
                    link_str = f" — [View Message](https://discord.com/channels/{guild_id}/{item.channel_id}/{item.discord_message_id})"

                lines.append(f"{prefix} **{item.topic}**")
                lines.append(f"Posted by <@{item.author_discord_id}> — {date_str}{link_str}")
                lines.append("")

            await interaction.response.send_message("\n".join(lines).strip())

    @tree.command(name="mystats", description="Show your challenge stats and earned badges.")
    async def mystats(interaction: discord.Interaction):
        with get_session() as session:
            student = (
                session.query(Student)
                .filter_by(discord_user_id=str(interaction.user.id))
                .one_or_none()
            )
            if student is None:
                await interaction.response.send_message(
                    "📊 You haven't made any challenge submissions yet. Post `Day 1: ...` to get started!"
                )
                return

            streak = session.query(Streak).filter_by(student_id=student.id).one_or_none()
            total_submissions = (
                session.query(Submission)
                .filter_by(student_id=student.id, is_valid=True)
                .count()
            )
            latest = (
                session.query(Submission)
                .filter_by(student_id=student.id, is_valid=True)
                .order_by(Submission.submission_date.desc())
                .first()
            )
            badges = (
                session.query(Achievement)
                .filter_by(student_id=student.id)
                .order_by(Achievement.earned_at.asc())
                .all()
            )

            current_streak_val = streak.current_streak if streak else 0
            best_streak_val = streak.best_streak if streak else 0
            latest_day_val = latest.challenge_day if latest else "—"
            last_date_val = (
                streak.last_submission_date.strftime("%d %B %Y")
                if (streak and streak.last_submission_date)
                else "—"
            )

            lines = [
                "📊 **YOUR CHALLENGE STATS**",
                "",
                f"🔥 Current streak: **{current_streak_val} days**",
                f"🏆 Best streak: **{best_streak_val} days**",
                f"📚 Latest challenge: **Day {latest_day_val}**",
                f"✅ Total submissions: **{total_submissions}**",
                f"📅 Last submission: **{last_date_val}**",
            ]

            if interaction.guild_id:
                settings = session.query(Settings).filter_by(guild_id=str(interaction.guild_id)).one_or_none()
                if settings and settings.challenge_started_date:
                    days_elapsed = (_today_local() - settings.challenge_started_date).days + 1
                    if days_elapsed > 0:
                        pct = min(round((total_submissions / days_elapsed) * 100, 1), 100.0)
                        lines.append(f"📈 Completion rate: **{pct}%**")

            lines.append("")
            lines.append("🏅 **BADGES**")
            if badges:
                for b in badges:
                    lines.append(f"🔥 {b.badge_name}")
            else:
                lines.append("No badges earned yet. Keep submitting daily to unlock badges!")

            await interaction.response.send_message("\n".join(lines))

    @tree.command(name="today", description="Show your challenge submission status for today.")
    async def today(interaction: discord.Interaction):
        with get_session() as session:
            today_date = _today_local()
            student = (
                session.query(Student)
                .filter_by(discord_user_id=str(interaction.user.id))
                .one_or_none()
            )

            submission = None
            streak = None
            if student:
                submission = (
                    session.query(Submission)
                    .filter_by(student_id=student.id, submission_date=today_date, is_valid=True)
                    .first()
                )
                streak = session.query(Streak).filter_by(student_id=student.id).one_or_none()

            current_streak = streak.current_streak if streak else 0

            if submission is not None:
                sub_time_local = submission.created_at.replace(tzinfo=dt.timezone.utc).astimezone(ZoneInfo(config.timezone))
                time_str = sub_time_local.strftime("%I:%M %p").lstrip("0")
                lines = [
                    "📅 **TODAY'S STATUS**",
                    "",
                    "Status: ✅ **Submitted**",
                    "",
                    f"Challenge: **Day {submission.challenge_day}**",
                    f"Submitted at: **{time_str}**",
                    f"Current streak: 🔥 **{current_streak} days**",
                ]
            else:
                lines = [
                    "📅 **TODAY'S STATUS**",
                    "",
                    "⚠️ You haven't submitted today's challenge yet.",
                    "",
                    f"Current streak: 🔥 **{current_streak} days**",
                ]

            await interaction.response.send_message("\n".join(lines))

    @tree.command(name="leaderboard", description="Show the challenge leaderboard by current streak.")
    async def leaderboard(interaction: discord.Interaction):
        with get_session() as session:
            rows = (
                session.query(Student, Streak)
                .join(Streak, Streak.student_id == Student.id)
                .filter(Student.active.is_(True))
                .order_by(Streak.current_streak.desc(), Streak.best_streak.desc())
                .limit(20)
                .all()
            )

            if not rows:
                await interaction.response.send_message("No submissions recorded yet.")
                return

            medals = ["🥇", "🥈", "🥉"]
            lines = ["🏆 **Challenge Leaderboard**", ""]
            for idx, (student, streak) in enumerate(rows):
                total_submissions = (
                    session.query(Submission)
                    .filter_by(student_id=student.id, is_valid=True)
                    .count()
                )
                prefix = medals[idx] if idx < 3 else f"{idx + 1}."
                lines.append(
                    f"{prefix} **{student.username}** — 🔥 {streak.current_streak} days "
                    f"(best: {streak.best_streak}, total: {total_submissions})"
                )

            await interaction.response.send_message("\n".join(lines))

    @tree.command(name="help", description="Show available challenge tracker commands.")
    async def help_command(interaction: discord.Interaction):
        user_is_trainer = check_user_is_trainer(interaction.user)

        lines = [
            "📖 **Akumen Challenge Tracker Commands**",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            "🎓 **STUDENT COMMANDS**",
            "• `/assignment` — Submit an assignment to the assignments channel",
            "• `/assignments` — View recent assignments",
            "• `/mystats` — View your challenge stats and earned badges",
            "• `/today` — Check your submission status for today",
            "• `/leaderboard` — View the top streak leaderboard",
            "• `/progress [student]` — View challenge progress for a student",
            "• `/help` — Show available commands",
            "• `/ping` — Check if the bot is online",
        ]

        if user_is_trainer:
            lines.extend([
                "",
                "🛡️ **TRAINER COMMANDS**",
                "• `/status` — View overall challenge participation status",
                "• `/missed` — List students who have not submitted today",
                "• `/reset [student]` — Reset a student's current streak",
                "• `/export` — Export student challenge data as CSV",
            ])

        lines.extend(["", "━━━━━━━━━━━━━━━━━━━━"])
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @tree.command(name="status", description="[Trainer] Show overall challenge status.")
    @is_trainer()
    async def status(interaction: discord.Interaction):
        with get_session() as session:
            today = _today_local()
            total_active = session.query(Student).filter(Student.active.is_(True)).count()

            submitted_today = (
                session.query(Submission)
                .join(Student, Student.id == Submission.student_id)
                .filter(
                    Submission.submission_date == today,
                    Submission.is_valid.is_(True),
                    Student.active.is_(True),
                )
                .count()
            )

            missing_today = max(total_active - submitted_today, 0)

            streaks = session.query(Streak).join(Student).filter(Student.active.is_(True)).all()
            longest = max((s.current_streak for s in streaks), default=0)
            average = round(sum(s.current_streak for s in streaks) / len(streaks), 1) if streaks else 0.0

            lines = [
                "📊 **Challenge Status**",
                "",
                f"Total active students: **{total_active}**",
                f"Submitted today: **{submitted_today}** ✅",
                f"Missing today: **{missing_today}** ❌",
                f"Longest current streak: **{longest} days**",
                f"Average current streak: **{average} days**",
            ]
            await interaction.response.send_message("\n".join(lines))

    @tree.command(name="missed", description="[Trainer] List active students who haven't submitted today.")
    @is_trainer()
    async def missed(interaction: discord.Interaction):
        with get_session() as session:
            today = _today_local()

            submitted_ids_subq = (
                session.query(Submission.student_id)
                .filter(Submission.submission_date == today, Submission.is_valid.is_(True))
                .subquery()
            )

            missing_students = (
                session.query(Student)
                .filter(Student.active.is_(True))
                .filter(Student.id.notin_(session.query(submitted_ids_subq.c.student_id)))
                .all()
            )

            if not missing_students:
                await interaction.response.send_message("✅ Everyone has submitted today!")
                return

            lines = ["⚠️ **Students who haven't submitted today**", ""]
            for student in missing_students:
                lines.append(f"• <@{student.discord_user_id}>")

            await interaction.response.send_message("\n".join(lines))

    @tree.command(name="progress", description="Show a student's challenge progress.")
    @app_commands.describe(student="The student to check")
    async def progress(interaction: discord.Interaction, student: discord.Member):
        with get_session() as session:
            db_student = (
                session.query(Student).filter_by(discord_user_id=str(student.id)).one_or_none()
            )
            if db_student is None:
                await interaction.response.send_message(
                    f"No submissions found for {student.mention} yet."
                )
                return

            streak = session.query(Streak).filter_by(student_id=db_student.id).one_or_none()
            total_submissions = (
                session.query(Submission)
                .filter_by(student_id=db_student.id, is_valid=True)
                .count()
            )
            latest = (
                session.query(Submission)
                .filter_by(student_id=db_student.id, is_valid=True)
                .order_by(Submission.submission_date.desc())
                .first()
            )

            lines = [
                f"📈 **Progress for {db_student.username}**",
                "",
                f"Current streak: **{streak.current_streak if streak else 0} days**",
                f"Best streak: **{streak.best_streak if streak else 0} days**",
                f"Total submissions: **{total_submissions}**",
                f"Latest challenge day: **{latest.challenge_day if latest else '—'}**",
                f"Last submission date: **{streak.last_submission_date if streak and streak.last_submission_date else '—'}**",
            ]
            await interaction.response.send_message("\n".join(lines))

    @tree.command(name="reset", description="[Trainer] Reset a student's current streak (keeps history).")
    @app_commands.describe(student="The student whose streak should be reset")
    @is_trainer()
    async def reset(interaction: discord.Interaction, student: discord.Member):
        with get_session() as session:
            db_student = (
                session.query(Student).filter_by(discord_user_id=str(student.id)).one_or_none()
            )
            if db_student is None:
                await interaction.response.send_message(
                    f"No record found for {student.mention}.", ephemeral=True
                )
                return

            streak = session.query(Streak).filter_by(student_id=db_student.id).one_or_none()
            if streak is None:
                await interaction.response.send_message(
                    f"No streak record found for {student.mention}.", ephemeral=True
                )
                return

            streak.current_streak = 0
            streak.last_submission_date = None
            # best_streak and all Submission rows are intentionally left untouched.

            await interaction.response.send_message(
                f"🔄 Current streak reset for {student.mention}. Historical submissions and best streak preserved."
            )

    @tree.command(name="export", description="[Trainer] Export all student data as CSV.")
    @is_trainer()
    async def export(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        with get_session() as session:
            rows = (
                session.query(Student, Streak)
                .join(Streak, Streak.student_id == Student.id)
                .order_by(Student.username)
                .all()
            )

            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(
                [
                    "username",
                    "discord_id",
                    "current_streak",
                    "best_streak",
                    "total_submissions",
                    "latest_challenge_day",
                    "last_submission_date",
                ]
            )

            for student, streak in rows:
                total_submissions = (
                    session.query(Submission)
                    .filter_by(student_id=student.id, is_valid=True)
                    .count()
                )
                latest = (
                    session.query(Submission)
                    .filter_by(student_id=student.id, is_valid=True)
                    .order_by(Submission.submission_date.desc())
                    .first()
                )
                writer.writerow(
                    [
                        student.username,
                        student.discord_user_id,
                        streak.current_streak,
                        streak.best_streak,
                        total_submissions,
                        latest.challenge_day if latest else "",
                        streak.last_submission_date or "",
                    ]
                )

            buffer.seek(0)
            file = discord.File(
                io.BytesIO(buffer.getvalue().encode("utf-8")),
                filename=f"challenge_export_{_today_local().isoformat()}.csv",
            )
            await interaction.followup.send("📄 Export ready:", file=file)

    @tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.exception("Slash command error", exc_info=error)
        message = "⚠️ Something went wrong running that command."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception:
            pass
