"""
Database engine + session management.

Version 1 uses SQLite via SQLAlchemy. This module is intentionally thin:
one engine, one sessionmaker, one helper to create tables. No migrations
framework in v1 — if the schema changes, wipe the dev DB or add a manual
migration step later (Alembic can be introduced when it's actually needed).
"""

import logging
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from bot.config import config
from bot.models import Base

logger = logging.getLogger(__name__)

# Ensure directory exists for file-based SQLite databases
if config.database_url.startswith("sqlite:///"):
    db_path = config.database_url.replace("sqlite:///", "")
    if db_path and db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

# check_same_thread=False is required because discord.py's async event loop
# and background tasks may touch the connection from different threads than
# the one that created it. We still only ever use short-lived sessions.
_connect_args = {"check_same_thread": False} if config.database_url.startswith("sqlite") else {}

engine = create_engine(config.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized at %s", config.database_url)


@contextmanager
def get_session() -> Session:
    """Context manager yielding a SQLAlchemy session with commit/rollback handling."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
