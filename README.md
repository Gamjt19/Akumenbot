# Discord Student Challenge & Streak Tracker Bot

A Discord bot that automatically tracks students' daily learning-challenge posts, calculates streaks, flags who missed a day, and gives trainers a leaderboard, status dashboard, and CSV export — all through Discord, no separate dashboard required.

---

## 1. What the bot does

Students post their daily progress in one designated channel, like:

> `Day 22: Completed Project 23 and 24`

The bot reads that message, figures out which student posted it, works out the **actual calendar date** from Discord's own message timestamp (not the day number the student typed), and updates that student's streak. It replies immediately with confirmation:

```
🔥 Day 22 recorded!

Student: Gamil
Current streak: 22 days
Best streak: 22 days
```

Trainers get commands to see who's behind, export data, and reset a stuck streak. A background task posts a daily summary automatically.

## 2. Features

- Automatic detection of `Day N: ...` submissions (case-insensitive, colon optional)
- Streak calculated from real calendar dates, never from the student's typed day number
- One official submission per student per day — duplicates are stored but don't double-count
- Missed-day detection resets current streak to 1 while preserving best streak
- Slash commands: `/ping`, `/leaderboard`, `/progress`, `/status`, `/missed`, `/reset`, `/export`
- Trainer/admin-only commands protected by Discord role (no hardcoded user IDs)
- Automatic daily report posted to an admin channel
- SQLite storage, fully working inside Docker with persistent data
- Streak logic is unit tested independently of Discord

## 3. Technology used

- Python 3.12+
- [discord.py](https://discordpy.readthedocs.io/) (slash commands via `app_commands`)
- SQLite via SQLAlchemy 2.x ORM
- python-dotenv for configuration
- pytest for tests
- Docker

## 4. Discord Developer Portal setup

You need a Discord "application" with a bot user before any of this works.

1. Go to https://discord.com/developers/applications and click **New Application**. Name it anything (e.g. "Challenge Tracker").
2. In the left sidebar, click **Bot**. Click **Reset Token** (or **Add Bot** if this is the first time) and copy the token somewhere safe — this is your `DISCORD_TOKEN`. **Never share this token or commit it to Git.**
3. On the same Bot page, scroll to **Privileged Gateway Intents** and enable:
   - **Message Content Intent** (required — the bot needs to read message text to parse submissions)
   - **Server Members Intent** (required — used for role checks and student lookups)
4. In the left sidebar, click **OAuth2 → URL Generator**.
   - Under **Scopes**, check `bot` and `applications.commands`.
   - Under **Bot Permissions**, check: `Send Messages`, `Read Message History`, `Use Slash Commands`, `Embed Links`, `Attach Files`.
5. Copy the generated URL at the bottom, open it in your browser, and choose the server to add the bot to.
6. In Discord, enable **Developer Mode** (User Settings → Advanced) so you can right-click any channel/server and "Copy ID". You'll need:
   - Your **server (guild) ID** → `GUILD_ID`
   - The **submission channel ID** (where students post) → `SUBMISSION_CHANNEL_ID`
   - The **admin/trainer channel ID** (for daily reports) → `ADMIN_CHANNEL_ID`
7. Create a role called `Trainer` (or set `TRAINER_ROLE_NAME` to match whatever you call it) and assign it to whoever should run admin commands.

## 5. Required Discord permissions

The bot's role needs, at minimum:
- View Channel
- Send Messages
- Read Message History
- Use Slash Commands
- Embed Links
- Attach Files (for `/export`)

## 6. Required environment variables

See `.env.example` for the full list with comments. Summary:

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Bot token from the Developer Portal |
| `DATABASE_URL` | No (default: `sqlite:///data/challenge.db`) | SQLAlchemy DB URL |
| `TIMEZONE` | No (default: `Asia/Kolkata`) | IANA timezone for day boundaries |
| `GUILD_ID` | Recommended | Enables instant slash-command sync to your server |
| `SUBMISSION_CHANNEL_ID` | Recommended | Channel the bot listens to for submissions |
| `ADMIN_CHANNEL_ID` | For daily reports | Channel the automatic report is posted to |
| `TRAINER_ROLE_NAME` | No (default: `Trainer`) | Role name granted admin-command access |
| `DAILY_REPORT_HOUR` / `DAILY_REPORT_MINUTE` | No (default: `21:00`) | Local time the daily report runs |

**Never commit your real `.env` file.** It's already listed in `.gitignore`.

## 7. Local installation

```bash
git clone <your-repo-url>
cd discord-challenge-tracker

python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# now edit .env and fill in your real DISCORD_TOKEN, GUILD_ID, channel IDs, etc.
```

## 8. Running locally

```bash
python -m bot.main
```

On first run this creates the SQLite database file automatically and syncs slash commands to your server (instant if `GUILD_ID` is set). You should see `Bot is ready.` in the logs. In Discord, try `/ping` — you should get `🏓 Pong! Bot is online.`

Then post a test message in your submission channel:

```
Day 1: Testing the bot
```

You should get a streak confirmation reply.

## 9. Running with Docker

Build the image:

```bash
docker build -t discord-challenge-bot .
```

Run it, mounting a volume so the SQLite database survives container restarts:

```bash
docker run -d \
  --name challenge-bot \
  --env-file .env \
  -v challenge_data:/app/data \
  discord-challenge-bot
```

Check logs:

```bash
docker logs -f challenge-bot
```

Stop it:

```bash
docker stop challenge-bot
```

Because `DATABASE_URL` defaults to `sqlite:///data/challenge.db` (a path relative to `/app` inside the container) and `data/` is a declared Docker `VOLUME`, your submission history and streaks persist even if you rebuild or recreate the container — as long as you keep using the same named volume (`challenge_data` above).

## 10. Database structure

**students** — one row per Discord user who has ever submitted
- `id`, `discord_user_id` (unique), `username`, `joined_at`, `active`

**submissions** — one row per message that matched the `Day N` pattern
- `id`, `student_id` (FK), `challenge_day`, `submission_date`, `message_id` (unique), `message_content`, `created_at`, `is_valid`
- `is_valid=True` means it's the official submission that counted toward the streak that day; later same-day posts are stored with `is_valid=False` for audit purposes.
- A unique constraint on `(student_id, submission_date, is_valid)` prevents more than one *official* submission per student per calendar date, even under race conditions.

**streaks** — one row per student
- `student_id` (PK/FK), `current_streak`, `best_streak`, `last_submission_date`

**settings** — one row per guild (for future multi-server support; v1 uses env vars as the primary config source)
- `guild_id` (PK), `submission_channel_id`, `admin_channel_id`, `timezone`, `challenge_started_date`

## 11. How streak calculation works

The core logic lives in `bot/streak_service.py` in a single pure function, `compute_next_streak`, that takes no Discord or database objects — just a `StreakState` (current streak, best streak, last submission date) and a new submission date. This makes it fully unit-testable in isolation (see `tests/test_streak.py`).

Rules:
- **First submission ever** → current streak = 1.
- **Previous submission was exactly 1 calendar day earlier** → current streak += 1.
- **A gap of 2+ calendar days** → current streak resets to 1 (best streak is preserved).
- **Best streak** is updated whenever the new current streak exceeds it.
- The student's self-typed `Day N` label is stored for display only — it is **never** used to calculate streaks or dates. Dates come from Discord's own `message.created_at` timestamp, converted into the configured `TIMEZONE` before being compared.
- Duplicate same-day posts are detected *before* reaching this function (in `bot/submission_service.py`) and never change the streak.

Worked example matching the spec:

```
Aug 1 → Day 1 → streak 1
Aug 2 → Day 2 → streak 2
Aug 3 → Day 3 → streak 3
Aug 4 → no submission
Aug 5 → Day 5 → new streak 1   (best streak stays 3)
```

## 12. Deploying to a free hosting environment

A few options that work well for a small always-on Discord bot:

**Railway.app** (simplest)
1. Push this repo to GitHub.
2. Create a new Railway project → "Deploy from GitHub repo".
3. Railway auto-detects the `Dockerfile`. Add all your `.env` variables under the project's **Variables** tab (do not upload the `.env` file itself).
4. Add a **Volume** mounted at `/app/data` so the SQLite database persists across deploys.
5. Deploy. Check logs for `Bot is ready.`

**Fly.io**
1. Install the `flyctl` CLI and run `fly launch` in this directory (it will detect the Dockerfile).
2. Run `fly volumes create challenge_data --size 1` and mount it at `/app/data` in `fly.toml`.
3. Set secrets: `fly secrets set DISCORD_TOKEN=... GUILD_ID=... SUBMISSION_CHANNEL_ID=... ADMIN_CHANNEL_ID=...`
4. `fly deploy`.

**Render.com**
1. New "Background Worker" service, connect your GitHub repo, select "Docker" as the environment.
2. Add environment variables in the dashboard.
3. Add a persistent disk mounted at `/app/data` (Render calls these "Disks", available on paid tiers — free tier storage is ephemeral, so on the free tier your streak data resets on redeploy; keep this in mind for a real cohort).

Whichever host you choose, the two things that matter are: (1) all `.env` values are set as real environment variables in the platform's dashboard, never committed to Git, and (2) `/app/data` is backed by *persistent* storage, not ephemeral container disk, or streak history will be lost on every redeploy/restart.

---

## Project structure

```
discord-challenge-tracker/
├── bot/
│   ├── __init__.py
│   ├── main.py                # entry point: bot setup, on_message handler
│   ├── config.py               # env var loading
│   ├── database.py             # SQLAlchemy engine/session
│   ├── models.py                # Student, Submission, Streak, Settings
│   ├── streak_service.py        # pure streak calculation logic
│   ├── submission_service.py    # parses + records a message, updates streak
│   ├── parser.py                # "Day N: ..." message parsing
│   ├── commands.py              # all slash commands
│   └── tasks.py                 # daily report background task
├── tests/
│   ├── test_streak.py
│   └── test_parser.py
├── .env.example
├── .gitignore
├── Dockerfile
├── requirements.txt
└── README.md
```

## Running the tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

All 22 tests (streak logic + parser) pass, covering: first submission, consecutive days, missed days, same-day duplicates, best-streak persistence across a break, the exact worked example from the spec, long gaps, independence between students, self-reported day numbers being ignored for streak math, and timezone/date-boundary correctness.
