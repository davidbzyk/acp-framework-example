
from collections.abc import AsyncGenerator
import json
import os

from acp_sdk.client import Client
from acp_sdk.models import Message, MessagePart, Metadata
from acp_sdk.server import RunYield, RunYieldResume, Server
from smolagents import (
    CodeAgent,
    DuckDuckGoSearchTool,
    LiteLLMModel,
    ToolCallingAgent,
    VisitWebpageTool,
)
from smolagents import tool as smoltool


# This server will host our main "Literary Critic" agent
server = Server()

# Define the model to be used by the agents
model = LiteLLMModel(model_id="openai/gpt-4o", max_tokens=4096)



# --- Define Specialist Tools & Agents ---

# 1. Historian Agent (Local)
historian_agent = CodeAgent(
    tools=[DuckDuckGoSearchTool(), VisitWebpageTool()], 
    model=model
)

# 2. Archivist Agent (Remote Tool via HTTP)
@smoltool
async def archivist_agent(input: str) -> str:
    """For specific, factual questions about a book's content.

    Args:
        input (str): A JSON string with 'book_title' and 'query'.
    """
    try:
        async with Client(base_url="http://127.0.0.1:8001") as client:
            run = await client.run_sync(
                agent="archivist_agent",
                input=[Message(parts=[MessagePart(content=input)])]
            )
            if run.output and run.output[0].parts:
                return run.output[0].parts[0].content
            return "Archivist returned no content."
    except Exception as e:
        return f"Error communicating with Archivist agent: {e}"


@server.agent(
    name="literary_critic_agent",
    metadata=Metadata(
        ui={"type": "hands-off", "user_greeting": "Ask about a book..."}
    ),
)
async def literary_critic_agent(
    input: list[Message],
) -> AsyncGenerator[RunYield, RunYieldResume]:
    """This is the Literary Critic agent. It orchestrates a team of specialist agents to answer complex questions about books."""

    # Catalog/discovery can be backed by filesystem (default) or MCP via ACP
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
    META_PATH = os.path.join(os.path.dirname(__file__), "book_metadata.json")
    USE_MCP = os.getenv("USE_MCP_DISCOVERY", "0") in {"1", "true", "True"}

    def _scan_books() -> list[str]:
        if not os.path.isdir(DATA_DIR):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(DATA_DIR)
            if f.endswith(".txt") and os.path.isfile(os.path.join(DATA_DIR, f))
        ]

    def _load_metadata() -> dict:
        try:
            with open(META_PATH, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except Exception:
            return {}

    if USE_MCP:
        @smoltool
        async def list_available_books() -> list[str]:
            """Returns a list of all book keys by querying the MCP catalog via ACP."""
            try:
                async with Client(base_url="http://127.0.0.1:8003") as client:
                    run = await client.run_sync(
                        agent="book_catalog_agent",
                        input=[Message(parts=[MessagePart(content="__LIST__")])],
                    )
                if run.output and run.output[0].parts:
                    return json.loads(run.output[0].parts[0].content)
            except Exception:
                pass
            # Fallback
            return _scan_books()

        @smoltool
        async def get_book_metadata(book_key: str) -> dict:
            """Return metadata for a given book by querying the MCP catalog via ACP; fallback to local JSON."""
            try:
                async with Client(base_url="http://127.0.0.1:8003") as client:
                    run = await client.run_sync(
                        agent="book_catalog_agent",
                        input=[Message(parts=[MessagePart(content=f"__META__:{book_key}")])],
                    )
                if run.output and run.output[0].parts:
                    return json.loads(run.output[0].parts[0].content)
            except Exception:
                pass
            # Fallback
            meta = _load_metadata()
            return meta.get(book_key, {})
    else:
        @smoltool
        async def list_available_books() -> list[str]:
            """Returns a list of all book keys (filenames without .txt) available in the library."""
            return _scan_books()

        @smoltool
        async def get_book_metadata(book_key: str) -> dict:
            """Return metadata for a given book key from local JSON.

            Args:
                book_key (str): The filename (without .txt) identifying the book in `ai_librarian/data/`.

            Returns:
                dict: Metadata object from `book_metadata.json` (e.g., title, author, year). Returns an empty dict if not found.
            """
            meta = _load_metadata()
            return meta.get(book_key, {})

        # Define a correctly named wrapper for the historian agent tool
    @smoltool
    def historian_agent_tool(query: str) -> str:
        """Use this for historical context, author information, or critical reception about a book or author.

        Args:
            query (str): A natural language question requesting background or historical/critical context.

        Returns:
            str: The historian agent's answer.
        """
        return historian_agent.run(query)

    all_tools = [
        list_available_books,
        get_book_metadata,
        archivist_agent,
        historian_agent_tool,
    ]

    agent = ToolCallingAgent(
        tools=all_tools,
        model=model,
        instructions='''You are a master literary critic and AI librarian. Delegate to specialist tools and agents to answer questions about books in the library.

YOUR AVAILABLE TOOLS:
- list_available_books(): List all book keys (filenames without .txt) in the library.
- get_book_metadata(book_key: str): Return metadata for a book (title, author, year, etc.).
- archivist_agent(input: str): For factual, text-based questions on a specific book. Input MUST be a JSON string with 'book_title' (a book key from list_available_books) and 'query'. Example: {"book_title": "mobydick", "query": "Who is Captain Ahab?"}.
- historian_agent_tool(query: str): For historical context, author bios, and critical reception.

PROCESS:
1. If unsure what is available, call list_available_books().
2. Identify the relevant book_key from the user's query.
3. Use archivist_agent for quotes/summaries from the text; use historian_agent_tool for context.
4. Optionally call get_book_metadata to enrich your answer (titles, authors, years).
5. Synthesize a cohesive response.

Always use tools to ground your answers. Do not invent book keys; only use those from list_available_books.''',
    )

    prompt = input[0].parts[0].content

    # Fast-path intents: directly list books when asked, without relying on LLM routing.
    lc = prompt.lower()
    if ("book" in lc or "library" in lc) and ("list" in lc or "available" in lc or "have" in lc):
        books = await list_available_books()
        if not books:
            content = "No books found in the library. Add .txt files to the ai_librarian/data/ folder."
        else:
            content = "Available books (use these keys):\n- " + "\n- ".join(sorted(books))
        yield Message(parts=[MessagePart(content=content)])
        return

    response = agent.run(prompt)

    yield Message(parts=[MessagePart(content=str(response))])


if __name__ == "__main__":
    server.run(port=8002)
