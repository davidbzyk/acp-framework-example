import asyncio
import json
import os
from typing import Tuple

from acp_sdk.client import Client
from acp_sdk.models import Message, MessagePart


AGENTS: dict[str, Tuple[str, str]] = {
    # name: (base_url, agent_name)
    "critic": ("http://127.0.0.1:8002", "literary_critic_agent"),
    "archivist": ("http://127.0.0.1:8001", "archivist_agent"),
    "catalog": ("http://127.0.0.1:8003", "book_catalog_server"),  # optional
}

ALIASES = {
    # Friendly human inputs map to normalized key
    "pride and prejudice": "prideandprejudice",
    "pride & prejudice": "prideandprejudice",
    # Backwards-compat: map the old typo key to the new normalized key
    "prideand predjudice": "prideandprejudice",
}

HERE = os.path.dirname(__file__)
META_PATH = os.path.join(HERE, "book_metadata.json")

def normalize_key(user_key: str) -> str:
    k = user_key.strip().lower()
    return ALIASES.get(k, k)

def load_metadata() -> dict:
    try:
        with open(META_PATH, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {}


async def call_agent(base_url: str, agent_name: str, content: str):
    async with Client(base_url=base_url) as client:
        run = await client.run_sync(
            agent=agent_name,
            input=[Message(parts=[MessagePart(content=content)])],
        )
        if run.output and run.output[0].parts:
            return run.output[0].parts[0].content
        if run.error:
            return f"[ERROR] {run.error}"
        return "[EMPTY RESPONSE]"


def print_banner(current: str):
    print("\nAI Librarian CLI (ACP Protocol Demo)")
    print("----------------------------------")
    print("Commands:")
    print("  /agents                List available agents")
    print("  /use <agent>          Switch active agent (critic | archivist | catalog)")
    print("  /list                 List available books (via critic or catalog)")
    print("  /meta <book_key>      Show metadata for a book (from book_metadata.json)")
    print("  /help                 Show help")
    print("  /exit                 Quit")
    print(f"\nActive agent: {current} -> {AGENTS[current][1]} @ {AGENTS[current][0]}")


async def interactive():
    current = "critic"
    print_banner(current)

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not user_input:
            continue

        if user_input.lower() in {"/exit", "exit", "quit", ":q"}:
            print("Goodbye!")
            break

        if user_input.lower() in {"/help", "help"}:
            print_banner(current)
            continue

        if user_input.lower() in {"/agents", "agents"}:
            for k, (url, name) in AGENTS.items():
                print(f"- {k}: {name} @ {url}")
            continue

        if user_input.lower().startswith("/use "):
            _, _, name = user_input.partition(" ")
            name = name.strip().lower()
            if name in AGENTS:
                current = name
                print(f"Switched to '{current}' -> {AGENTS[current][1]} @ {AGENTS[current][0]}")
            else:
                print(f"Unknown agent '{name}'. Try one of: {', '.join(AGENTS.keys())}")
            continue

        if user_input.lower().startswith("/meta "):
            _, _, key = user_input.partition(" ")
            key = normalize_key(key)
            meta = load_metadata().get(key)
            if not meta:
                print(f"No metadata found for '{key}'.")
            else:
                print(json.dumps(meta, indent=2, ensure_ascii=False))
            continue

        if user_input.lower() in {"/list", "list"}:
            # Prefer critic to list, otherwise fall back to catalog
            if "critic" in AGENTS:
                url, agent_name = AGENTS["critic"]
                prompt = "List the available books."
            else:
                url, agent_name = AGENTS["catalog"]
                prompt = "list_available_books"
            print("\n[Request]", agent_name, "<=", prompt)
            print("[Response]", await call_agent(url, agent_name, prompt))
            continue

        # Normal question flow
        url, agent_name = AGENTS[current]

        # Archivist expects a JSON string with 'book_title' and 'query'
        if current == "archivist":
            # If user already provided JSON, trust it; else guide them
            try:
                _ = json.loads(user_input)
                payload = user_input
            except json.JSONDecodeError:
                book_key = normalize_key(input("Book key (e.g., mobydick, frankenstein): ").strip())
                payload = json.dumps({
                    "book_title": book_key,
                    "query": user_input,
                })
            print("\n[Request]", agent_name, "<=", payload)
            print("[Response]", await call_agent(url, agent_name, payload))
            continue

        # Critic or Catalog (or any other) accept plain strings
        print("\n[Request]", agent_name, "<=", user_input)
        print("[Response]", await call_agent(url, agent_name, user_input))


if __name__ == "__main__":
    asyncio.run(interactive())
