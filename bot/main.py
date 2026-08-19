"""
Bot entry point.

Wires together config, database, commands, background tasks, and the
on_message handler that detects daily challenge submissions.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.commands import setup_commands
from bot.config import config
from bot.database import get_session, init_db
from bot.submission_service import SubmissionOutcome, SubmissionResult, process_message
from bot.tasks import setup_daily_report_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("challenge_bot")

intents = discord.Intents.default()
intents.message_content = True
intents.members = False

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "unknown")

    try:
        if config.guild_id:
            try:
                guild = discord.Object(id=config.guild_id)
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                logger.info("Synced %d slash commands to guild %s", len(synced), config.guild_id)
            except Exception as e:
                logger.warning("Could not sync to guild %s (%s). Falling back to global sync.", config.guild_id, e)
                synced = await bot.tree.sync()
                logger.info("Synced %d global slash commands", len(synced))
        else:
            synced = await bot.tree.sync()
            logger.info("Synced %d global slash commands", len(synced))
    except Exception:
        logger.exception("Failed to sync slash commands")

    setup_daily_report_task(bot)
    logger.info("Bot is ready.")


@bot.event
async def on_message(message: discord.Message):
    # Never process the bot's own messages.
    if message.author.bot:
        return

    logger.info("Message received from %s (channel_id=%s): %r", message.author, message.channel.id, message.content)

    # Only look at the configured submission channel, if one is set.
    if config.submission_channel_id is not None and message.channel.id != config.submission_channel_id:
        logger.info(
            "Ignored message: channel_id %s does not match SUBMISSION_CHANNEL_ID %s",
            message.channel.id,
            config.submission_channel_id,
        )
        return

    try:
        with get_session() as session:
            result = process_message(
                session,
                discord_user_id=str(message.author.id),
                username=message.author.display_name,
                message_id=str(message.id),
                message_content=message.content,
                message_timestamp_utc=message.created_at,
                timezone_name=config.timezone,
            )

        if result.outcome == SubmissionOutcome.RECORDED:
            broken_note = "\n_A day was missed, so this starts a new streak._" if result.streak_broken else ""
            await message.reply(
                f"🔥 **Day {result.challenge_day} recorded!**\n\n"
                f"Student: {message.author.display_name}\n"
                f"Current streak: **{result.current_streak} days**\n"
                f"Best streak: **{result.best_streak} days**"
                f"{broken_note}"
            )

            # Public announcement for newly unlocked achievements
            if result.new_achievements:
                try:
                    ach_channel_id = config.achievements_channel_id or config.submission_channel_id
                    if ach_channel_id:
                        ach_channel = bot.get_channel(ach_channel_id)
                        if ach_channel is None:
                            try:
                                ach_channel = await bot.fetch_channel(ach_channel_id)
                            except Exception:
                                ach_channel = None

                        if ach_channel:
                            for badge_name in result.new_achievements:
                                await ach_channel.send(
                                    f"🏆 **ACHIEVEMENT UNLOCKED!**\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"🎉 Congratulations <@{message.author.id}>! You earned the **{badge_name}** badge!\n"
                                    f"━━━━━━━━━━━━━━━━━━━━"
                                )
                except Exception:
                    logger.exception("Failed to send achievement announcement")
        elif result.outcome == SubmissionOutcome.DUPLICATE_SAME_DAY:
            await message.reply(
                "You've already logged a submission for today — this one was recorded "
                "but won't count twice toward your streak."
            )
        elif result.outcome == SubmissionOutcome.INVALID_DAY_NUMBER:
            await message.reply(
                f"⚠️ **Invalid day number!**\n\n"
                f"Expected **Day {result.expected_day}**, but you entered **Day {result.challenge_day}**.\n"
                f"Please re-submit using `Day {result.expected_day}`."
            )
        elif result.outcome == SubmissionOutcome.STREAK_BROKEN_MUST_RESTART:
            last_day_info = f" (your last submission was **Day {result.last_valid_day}**)" if result.last_valid_day else ""
            await message.reply(
                f"❌ **Streak broken — you must restart from Day 1!**\n\n"
                f"You missed one or more days{last_day_info}, so your streak and day counter have been reset.\n\n"
                f"Please re-submit using `Day 1: <your progress>` to begin a new streak. 💪"
            )
        # NOT_A_SUBMISSION: silently ignored on purpose (channel may have other
        # chatter). If stricter behavior is wanted, uncomment the else-branch below.
        # else:
        #     await message.reply(
        #         "⚠️ I couldn't find a day number. Try: `Day 22: Completed Project 23 and 24`"
        #     )

    except Exception:
        # A single bad message must never crash the bot.
        logger.exception("Error processing message %s from %s", message.id, message.author.id)

    # Allow prefix commands (e.g. future admin utilities) to still work.
    await bot.process_commands(message)


def main() -> None:
    init_db()
    setup_commands(bot)
    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
