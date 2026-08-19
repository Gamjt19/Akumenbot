import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.models import Assignment, Base


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


def test_assignment_creation(db_session):
    assignment = Assignment(
        author_discord_id="123456789",
        author_username="Gamil",
        topic="Docker Networking",
        details="Complete the Docker networking exercise.",
        created_at=dt.datetime.now(dt.timezone.utc),
        discord_message_id="msg_999",
        channel_id="chan_888",
    )
    db_session.add(assignment)
    db_session.commit()

    saved = db_session.query(Assignment).filter_by(topic="Docker Networking").first()
    assert saved is not None
    assert saved.author_username == "Gamil"
    assert saved.author_discord_id == "123456789"
    assert saved.details == "Complete the Docker networking exercise."
    assert saved.discord_message_id == "msg_999"


def test_assignment_retrieval_limit_and_order(db_session):
    # Insert 12 assignments with staggered timestamps
    now = dt.datetime(2026, 8, 15, 12, 0)
    for i in range(12):
        item = Assignment(
            author_discord_id=f"user_{i}",
            author_username=f"Student_{i}",
            topic=f"Topic {i}",
            details=f"Details for topic {i}",
            created_at=now + dt.timedelta(minutes=i),
            discord_message_id=f"msg_{i}",
            channel_id="chan_1",
        )
        db_session.add(item)
    db_session.commit()

    # Query latest 10
    recent = (
        db_session.query(Assignment)
        .order_by(Assignment.created_at.desc())
        .limit(10)
        .all()
    )

    assert len(recent) == 10
    assert recent[0].topic == "Topic 11"  # Most recent first
    assert recent[9].topic == "Topic 2"


def test_assignment_multiline_details_preservation(db_session):
    multiline_text = (
        "Does anyone know why this is happening and how I can fix it?\n\n"
        "1. Check the Docker configuration\n"
        "2. Check the network\n"
        "3. Rebuild the image"
    )
    assignment = Assignment(
        author_discord_id="123456789",
        author_username="Gamil",
        topic="Project 34",
        details=multiline_text,
        created_at=dt.datetime(2026, 8, 19, 11, 0, tzinfo=dt.timezone.utc),
        discord_message_id="msg_multiline_1",
        channel_id="chan_post_1",
    )
    db_session.add(assignment)
    db_session.commit()

    saved = db_session.query(Assignment).filter_by(discord_message_id="msg_multiline_1").first()
    assert saved is not None
    assert saved.topic == "Project 34"
    assert saved.details == multiline_text
    assert "\n" in saved.details
    assert saved.details.splitlines() == [
        "Does anyone know why this is happening and how I can fix it?",
        "",
        "1. Check the Docker configuration",
        "2. Check the network",
        "3. Rebuild the image",
    ]


def test_format_post_message():
    from bot.commands import format_post_message

    topic = "Project 34"
    details = (
        "Do hosting in azure\n\n"
        "1. host protfoilio\n"
        "2. fix ssl\n"
        "3. take ss and submit"
    )
    author_id = "987654321"
    posted_str = "19 Aug 2026, 04:30 PM"

    formatted = format_post_message(
        topic=topic,
        details=details,
        author_id=author_id,
        posted_str=posted_str,
    )

    expected = (
        "📌 **Project 34**\n\n"
        "Do hosting in azure\n\n"
        "1. host protfoilio\n"
        "2. fix ssl\n"
        "3. take ss and submit\n\n"
        "👤 **Posted by:** <@987654321>\n"
        "🕒 **Posted:** 19 Aug 2026, 04:30 PM"
    )

    assert formatted == expected
    assert "NEW ASSIGNMENT" not in formatted
    assert "📚" not in formatted


def test_create_post_modal_fields():
    import discord
    from unittest.mock import MagicMock
    from bot.commands import CreatePostModal

    bot = MagicMock()
    modal = CreatePostModal(bot=bot)

    assert modal.title == "Create Post"
    assert modal.topic.label == "Topic"
    assert modal.topic.style == discord.TextStyle.short
    assert modal.topic.required is True
    assert modal.details.label == "Details"
    assert modal.details.style in (discord.TextStyle.paragraph, discord.TextStyle.long)
    assert modal.details.required is True


def test_create_post_modal_empty_validation():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from bot.commands import CreatePostModal

    bot = MagicMock()
    modal = CreatePostModal(bot=bot)
    modal.topic = MagicMock()
    modal.details = MagicMock()

    # Case 1: Empty topic
    modal.topic.value = "   "
    modal.details.value = "Some valid details"
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()

    asyncio.run(modal.on_submit(interaction))
    interaction.response.send_message.assert_awaited_once_with(
        "❌ Topic and details cannot be empty.",
        ephemeral=True,
    )

    # Case 2: Empty details
    modal.topic.value = "Valid Topic"
    modal.details.value = "   \n\n  "
    interaction.response.send_message.reset_mock()

    asyncio.run(modal.on_submit(interaction))
    interaction.response.send_message.assert_awaited_once_with(
        "❌ Topic and details cannot be empty.",
        ephemeral=True,
    )


def test_create_post_modal_success(monkeypatch, db_session):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from bot.commands import CreatePostModal

    bot = MagicMock()
    channel = MagicMock()
    sent_msg = MagicMock()
    sent_msg.id = 555666777
    channel.send = AsyncMock(return_value=sent_msg)
    bot.get_channel.return_value = channel

    import contextlib
    import dataclasses
    from bot.config import config
    mock_config = dataclasses.replace(config, assignments_channel_id=11223344)
    monkeypatch.setattr("bot.commands.config", mock_config)

    @contextlib.contextmanager
    def fake_session():
        yield db_session

    monkeypatch.setattr("bot.commands.get_session", fake_session)

    modal = CreatePostModal(bot=bot)
    modal.topic = MagicMock()
    modal.topic.value = "Docker Task"
    modal.details = MagicMock()
    modal.details.value = "Step 1: Build image\nStep 2: Run container"

    interaction = MagicMock()
    interaction.user.id = 998877
    interaction.user.display_name = "TrainerAlice"
    interaction.response.send_message = AsyncMock()

    asyncio.run(modal.on_submit(interaction))

    # Verify channel.send was called with formatted post containing newlines
    channel.send.assert_awaited_once()
    sent_text = channel.send.call_args[0][0]
    assert "📌 **Docker Task**" in sent_text
    assert "Step 1: Build image\nStep 2: Run container" in sent_text
    assert "👤 **Posted by:** <@998877>" in sent_text
    assert "NEW ASSIGNMENT" not in sent_text

    # Verify record was stored in database
    record = db_session.query(Assignment).filter_by(discord_message_id="555666777").first()
    assert record is not None
    assert record.author_discord_id == "998877"
    assert record.author_username == "TrainerAlice"
    assert record.topic == "Docker Task"
    assert record.details == "Step 1: Build image\nStep 2: Run container"
    assert record.channel_id == "11223344"

    # Verify user interaction response
    interaction.response.send_message.assert_awaited_once()
    response_text = interaction.response.send_message.call_args[0][0]
    assert "✅ Post created successfully!" in response_text
    assert "<#11223344>" in response_text

