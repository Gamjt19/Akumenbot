import pytest

from bot.parser import parse_submission


def test_valid_day_with_colon():
    result = parse_submission("Day 22: Completed Project 23 and 24")
    assert result is not None
    assert result.challenge_day == 22
    assert result.note == "Completed Project 23 and 24"


def test_valid_day_lowercase():
    result = parse_submission("day 22: completed docker project")
    assert result is not None
    assert result.challenge_day == 22


def test_valid_day_uppercase():
    result = parse_submission("DAY 22: COMPLETED PROJECT")
    assert result is not None
    assert result.challenge_day == 22


def test_valid_day_without_colon():
    result = parse_submission("Day 22 Completed Project 23 and 24")
    assert result is not None
    assert result.challenge_day == 22
    assert result.note == "Completed Project 23 and 24"


def test_valid_day_zero_padded():
    result = parse_submission("Day 01: First day!")
    assert result is not None
    assert result.challenge_day == 1


def test_missing_day_number_is_invalid():
    assert parse_submission("Completed Docker project") is None


def test_day_mentioned_mid_sentence_is_invalid():
    # Must be structured as a day-log post, not just mention "day" somewhere.
    assert parse_submission("I finished Day 22 of the challenge today") is None


def test_empty_message_is_invalid():
    assert parse_submission("") is None


def test_whitespace_only_message_is_invalid():
    assert parse_submission("   ") is None


def test_day_word_without_number_is_invalid():
    assert parse_submission("Day: Completed stuff") is None


def test_leading_whitespace_tolerated():
    result = parse_submission("   Day 5: something")
    assert result is not None
    assert result.challenge_day == 5


def test_no_note_after_day_number():
    result = parse_submission("Day 22")
    assert result is not None
    assert result.challenge_day == 22
    assert result.note == ""
