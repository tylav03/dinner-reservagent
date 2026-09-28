"""Talk to the reservation agent in the terminal — no audio, just text and
tool calls against the real database. This is where the conversation and
tool-calling logic gets worked out cheaply, before Phase 4 adds a microphone
and Phase 5 adds a phone number.

    python -m scripts.text_agent

Each run is one "call": a single DB session for the whole conversation, and
one idempotency key (stands in for what will be the Twilio Call SID from
Phase 5 onward) so a retried create_reservation tool call can't double-book.
The agent speaks first, same as answering a real phone call would.

Type 'quit' / 'exit' / Ctrl-D to hang up.
"""

from __future__ import annotations

import json
import sys
import uuid

from app.config import get_settings
from app.db import session_scope
from app.voice.prompts import build_system_prompt
from app.voice.tools import TOOL_SCHEMAS, call_tool

MAX_TOOL_ROUNDS = 5  # per turn — a safety valve against a runaway tool-call loop


def _print_tool_call(name: str, args: dict, result: dict) -> None:
    print(f"  \033[2m[tool] {name}({json.dumps(args)}) -> {json.dumps(result)}\033[0m")


def _run_agent_turn(client, session, settings, messages: list[dict], call_id: str) -> None:
    """Get the agent's next turn, resolving any tool calls along the way, and
    print/append its final spoken response. Used both for the opening greeting
    (no user message yet) and for every reply after that — same logic either
    way, so the greeting gets exactly the same tool-calling behavior as the
    rest of the conversation.
    """
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content})
            print(f"Agent: {msg.content}\n")
            return

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            if tc.function.name == "create_reservation":
                args.setdefault("idempotency_key", call_id)
            result = call_tool(session, tc.function.name, args)
            _print_tool_call(tc.function.name, args, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })

    print("Agent: [gave up after too many tool calls in one turn — something's looping]\n")


def main() -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        print(
            "OPENAI_API_KEY isn't set. Add it to .env, then re-run:\n"
            "    OPENAI_API_KEY=sk-...\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        from openai import OpenAI
    except ImportError:
        print("The openai package isn't installed. Run: pip install -r requirements.txt",
              file=sys.stderr)
        raise SystemExit(1) from None

    client = OpenAI(api_key=settings.openai_api_key)
    call_id = str(uuid.uuid4())  # this call's idempotency key
    messages: list[dict] = [{"role": "system", "content": build_system_prompt()}]

    print(f"Connected. Model: {settings.openai_model}. Type 'quit' to hang up.\n")

    with session_scope() as session:
        # The agent answers the call — it speaks first, before any user input.
        _run_agent_turn(client, session, settings, messages, call_id)

        while True:
            try:
                user_text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[call ended]")
                return
            if user_text.lower() in {"quit", "exit", "bye", "hang up"}:
                print("[call ended]")
                return
            if not user_text:
                continue

            messages.append({"role": "user", "content": user_text})
            _run_agent_turn(client, session, settings, messages, call_id)


if __name__ == "__main__":
    main()
