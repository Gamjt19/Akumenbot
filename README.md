# Akumen Challenge Tracker Bot

A production Discord bot for tracking daily learning-challenge posts, student streaks, assignment submissions, milestones & badges, and automated daily participation reports — built with Python, discord.py, SQLAlchemy, and PostgreSQL (Supabase).

---

## 1. Features & Overview

- **Daily Challenge Submissions**: Automatically parses `Day N: ...` updates in the submission channel and calculates streaks based on real calendar dates in the configured timezone (`Asia/Kolkata`).
- **00:05 Daily Summary Report**: Automatically generates and posts a comprehensive participation report at `00:05` summarizing the **previous calendar day** to the trainer channel with zero duplicate deliveries.
- **Assignment Submission (`/assignment` & `/assignments`)**: Allows students to submit assignments via slash commands which the bot posts into a dedicated assignments channel on their behalf.
- **Student Stats & Badges (`/mystats`)**: Tracks streaks, submission history, and awards milestone badges (7-day, 14-day, 30-day, 50-day, 100-day streaks, and submission milestones).
- **Today's Status (`/today`)**: Gives students instant feedback on whether they have submitted their challenge for today.
- **Dynamic Help Menu (`/help`)**: Lists student commands for all users and reveals trainer commands only to authorized trainers and administrators.
- **Leaderboard (`/leaderboard`)**: Ranks students by current streak, best streak, and total submissions.
- **Trainer Commands**: `/status`, `/missed`, `/reset`, and `/export` for monitoring cohort progress and exporting CSV data.

---

## 2. Slash Commands

### Student Commands
| Command | Arguments | Description |
|---|---|---|
| `/assignment` | `topic: str, details: str` | Submit an assignment. The bot posts it to the configured assignments channel on your behalf. |
| `/assignments` | None | View recent assignment posts with direct message links. |
| `/mystats` | None | View your current streak, best streak, total submissions, latest day, and unlocked badges. |
| `/today` | None | Check your submission status for the current calendar day. |
| `/leaderboard` | None | View top students ranked by current streak and best streak. |
| `/progress` | `student: Member` | View challenge progress for a specific student. |
| `/help` | None | Show available commands (dynamically filtered by role). |
| `/ping` | None | Check bot connectivity and responsiveness. |

### Trainer Commands (Restricted to `TRAINER_ROLE_NAME` or Admins)
| Command | Arguments | Description |
|---|---|---|
| `/status` | None | View total active students, today's submission counts, and longest streaks. |
| `/missed` | None | List students who have not yet submitted today's challenge. |
| `/reset` | `student: Member` | Reset a student's current streak (preserves historical submissions and best streak). |
| `/export` | None | Export all student challenge data to a CSV file. |

---

## 3. Daily Report (00:05 Asia/Kolkata)

The automated daily report runs every day at **00:05 Asia/Kolkata** (configured via `DAILY_REPORT_HOUR=0` and `DAILY_REPORT_MINUTE=5`).

- **Previous Day Summary**: At `00:05` on August 16, the report summarizes submissions from **August 15**. It excludes August 16 submissions.
- **Deterministic & DB-Driven**: Submissions are queried directly from the database for the target calendar date, eliminating redundant Discord message history scans.
- **Deduplication Protection**: Report deliveries are tracked in the `daily_reports` table so restarts or reconnects after 00:05 never send duplicate reports.
- **Posted To**: `TRAINER_CHANNEL_ID` (or legacy `ADMIN_CHANNEL_ID`).

**Report Format**:
```
📊 DAILY CHALLENGE REPORT
━━━━━━━━━━━━━━━━━━━━

📅 Date: 15 August 2026

👥 Total Students: 42
✅ Submitted: 38
❌ Missing: 4
📈 Completion: 90.5%

🔥 TOP STREAKS

🥇 @Rahul — 31 days
🥈 @Gamil — 24 days
🥉 @Anu — 19 days

✅ SUBMITTED

@Rahul — Day 31 — 🔥 31
@Gamil — Day 24 — 🔥 24
...

❌ NOT SUBMITTED

@Vishnu
@Meera
@Arjun

━━━━━━━━━━━━━━━━━━━━
```

---

## 4. Assignment Submission Flow

Students often have access to a common Discord chat but cannot post directly to a read-only announcements/assignments channel.

1. Student runs:
   ```
   /assignment topic:"Docker Networking" details:"Complete the Docker networking exercise"
   ```
2. The bot verifies the student's input, formats a clean assignment post, and sends it to `ASSIGNMENTS_CHANNEL_ID`:
   ```
   📚 NEW ASSIGNMENT
   ━━━━━━━━━━━━━━━━━━━━

   📌 Topic:
   Docker Networking

   📝 Details:
   Complete the Docker networking exercise

   👤 Posted by:
   @StudentName

   🕒 Posted:
   15 August 2026, 11:45 PM

   ━━━━━━━━━━━━━━━━━━━━
   ```
3. The bot records the assignment in the `assignments` database table.
4. The student receives an ephemeral confirmation message visible only to them.

---

## 5. Achievements & Badges

Milestone badges are awarded automatically when a student logs a valid submission:
- **First Challenge** (1st valid submission)
- **7 Day Streak** (streak ≥ 7)
- **14 Day Streak** (streak ≥ 14)
- **30 Day Streak** (streak ≥ 30)
- **50 Day Streak** (streak ≥ 50)
- **100 Day Streak** (streak ≥ 100)
- **10 Submissions**, **25 Submissions**, **50 Submissions**, **100 Submissions**

When unlocked for the first time, the bot announces the achievement in `ACHIEVEMENTS_CHANNEL_ID` (or `SUBMISSION_CHANNEL_ID` if unconfigured). Badges are stored in the `achievements` table with a unique constraint to ensure they are never awarded twice.

---

## 6. Required Discord Permissions

The bot's Discord role requires the following permissions:
- **View Channels**
- **Send Messages** (specifically in `ASSIGNMENTS_CHANNEL_ID`, `TRAINER_CHANNEL_ID`, `ACHIEVEMENTS_CHANNEL_ID`, and `SUBMISSION_CHANNEL_ID`)
- **Embed Links**
- **Read Message History**
- **Attach Files** (for `/export` CSV files)
- **Use Slash Commands**

Students do **not** need `Send Messages` permission in `ASSIGNMENTS_CHANNEL_ID`.

---

## 7. Environment Variables

Configure these variables in your environment or `.env` file (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | *Required* | Bot token from the Discord Developer Portal |
| `DB_URL` / `DATABASE_URL` | *Required* | Supabase / PostgreSQL database connection URL |
| `TIMEZONE` | `Asia/Kolkata` | IANA timezone for calendar day boundaries & reporting |
| `GUILD_ID` | `None` | Discord Server ID for instant slash command synchronization |
| `SUBMISSION_CHANNEL_ID` | `None` | Channel ID where students submit daily `Day N: ...` updates |
| `TRAINER_CHANNEL_ID` | `None` | Channel ID where daily challenge reports are posted |
| `ASSIGNMENTS_CHANNEL_ID` | `None` | Channel ID where student assignments are posted by the bot |
| `ACHIEVEMENTS_CHANNEL_ID` | `None` | Channel ID where unlocked achievement badges are announced |
| `TRAINER_ROLE_NAME` | `trainer` | Role name granted trainer command permissions |
| `DAILY_REPORT_HOUR` | `0` | Hour of the day for the daily report (0-23) |
| `DAILY_REPORT_MINUTE` | `5` | Minute of the hour for the daily report (0-59) |

---

## 8. Database Tables (Supabase / PostgreSQL)

1. **`students`**: User identity and active status (`id`, `discord_user_id`, `username`, `joined_at`, `active`).
2. **`submissions`**: Validated challenge posts (`id`, `student_id`, `challenge_day`, `submission_date`, `message_id`, `message_content`, `created_at`, `is_valid`).
3. **`streaks`**: Real-time streak tracking (`student_id`, `current_streak`, `best_streak`, `last_submission_date`).
4. **`assignments`**: Assignment submissions (`id`, `author_discord_id`, `author_username`, `topic`, `details`, `created_at`, `discord_message_id`, `channel_id`).
5. **`achievements`**: Earned milestone badges (`id`, `student_id`, `badge_key`, `badge_name`, `earned_at`).
6. **`daily_reports`**: Historical record of daily reports sent (`id`, `report_date`, `sent_at`, `channel_id`).
7. **`settings`**: Guild-level configurations.

---

## 9. Running the Bot & Tests

### Running locally
```bash
python main.py
```

### Running unit tests
```bash
pytest -v
```
