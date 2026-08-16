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
