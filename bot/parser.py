"""
Parses raw Discord message content to detect valid challenge submissions.

A valid submission looks like:
    Day 22: Completed Project 23 and 24
    day 22 Completed Docker project
    DAY 01: ...

The day number is required. Case is ignored. The colon is optional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches "Day" (any case) + whitespace + digits, optionally followed by
# ":" or more text. Anchored to the start of the message (after stripping
# leading whitespace) so "I finished Day 22" does NOT count — the message
# must actually be structured as a day-log post, not just mention a day.
_DAY_PATTERN = re.compile(r"^\s*day\s+(\d{1,4})\b\s*:?\s*(.*)$", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class ParsedSubmission:
    challenge_day: int
    note: str


def parse_submission(content: str) -> ParsedSubmission | None:
    """
    Attempt to parse a message as a valid challenge submission.

    Returns a ParsedSubmission if valid, otherwise None.
    """
    if not content:
        return None

    match = _DAY_PATTERN.match(content)
    if not match:
        return None

    day_str, note = match.groups()

    try:
        day_number = int(day_str)
    except ValueError:
        return None

    if day_number <= 0:
        return None

    return ParsedSubmission(challenge_day=day_number, note=note.strip())
