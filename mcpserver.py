"""
ACP Catalog Server ("MCP-like")

This server exposes discovery and metadata endpoints over ACP HTTP so other agents
can consume them via the acp_sdk Client. It supports two commands via a single agent:

- "__LIST__" -> returns a JSON array of book keys
- "__META__:<book_key>" -> returns a JSON object with metadata for the book (or {})

Backed by either a local JSON file (book_metadata.json) or a remote JSON URL when
BOOK_METADATA_URL is set. Falls back to scanning data/*.txt for keys if metadata
is missing.
"""

import json
import os
from typing import Dict, List

from acp_sdk.models import Message, MessagePart
from acp_sdk.server import Server

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
LOCAL_META_PATH = os.path.join(BASE_DIR, "book_metadata.json")

def load_metadata() -> Dict[str, dict]:
    url = os.getenv("BOOK_METADATA_URL")
    if url:
        try:
            import requests  # lazy import
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            pass  # fall back to local
    try:
        with open(LOCAL_META_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def scan_books() -> List[str]:
    if not os.path.isdir(DATA_DIR):
        return []
    return [
        os.path.splitext(f)[0]
        for f in os.listdir(DATA_DIR)
        if f.endswith(".txt") and os.path.isfile(os.path.join(DATA_DIR, f))
    ]

server = Server()

@server.agent(name="book_catalog_agent")
def book_catalog_agent(input: list[Message]):
    prompt = input[0].parts[0].content if input and input[0].parts else ""
    metadata = load_metadata()
    if prompt == "__LIST__":
        # Prefer keys from metadata; otherwise use filesystem scan
        keys = list(metadata.keys()) or scan_books()
        return [Message(parts=[MessagePart(content=json.dumps(sorted(keys)))])]
    if prompt.startswith("__META__:"):
        key = prompt.split(":", 1)[1]
        meta = metadata.get(key, {})
        return [Message(parts=[MessagePart(content=json.dumps(meta))])]
    return [Message(parts=[MessagePart(content="{}")])]

if __name__ == "__main__":
    server.run(port=8003)
