"""The agent's system prompt. Pure string building — no DB, no LLM."""

from __future__ import annotations

from datetime import datetime

from app.voice.prompts import build_system_prompt


def test_prompt_has_no_doubled_spaces():
    # Regression: backslash-continued lines that were indented in source for
    # readability leaked their indentation into the actual prompt text
    # ("Never    guess" instead of "Never guess").
    prompt = build_system_prompt()
    assert "  " not in prompt.replace("\n\n", "")


def test_prompt_reflects_the_given_now():
    prompt = build_system_prompt(now=datetime(2026, 9, 22, 16, 48))
    assert "Tuesday, September 22, 2026" in prompt
    assert "4:48 PM" in prompt


def test_prompt_includes_key_restaurant_facts():
    prompt = build_system_prompt()
    assert "The Copper Fork" in prompt
    assert "Monday: closed" in prompt
    assert "90 minutes" in prompt
    assert "8" in prompt  # max party size
    assert "check_availability" in prompt  # tool name referenced in the rules
