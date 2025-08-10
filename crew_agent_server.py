from collections.abc import AsyncGenerator
from acp_sdk.models import Message, MessagePart, Metadata
from acp_sdk.server import RunYield, RunYieldResume, Server
import json
import os

from crewai import Crew, Task, Agent, LLM
from crewai_tools import RagTool

import nest_asyncio

nest_asyncio.apply()

server = Server()
llm = LLM(model="openai/gpt-4o", max_tokens=1024)

config = {
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gpt-4o",
        },
    },
    "embedding_model": {
        "provider": "openai",
        "config": {"model": "text-embedding-ada-002"},
    },
}
@server.agent(
    name="archivist_agent",
    metadata=Metadata(
        ui={"type": "hands-off", "user_greeting": "I am the Archivist. Ask me a question about a specific book."}
    )
)
async def archivist_agent(
    input: list[Message],
) -> AsyncGenerator[RunYield, RunYieldResume]:
    """This is the Archivist agent. It uses a RAG pipeline to answer factual questions about a specific book. Expects a JSON string with 'book_title' and 'query'."""
    
    # Parse the incoming request
    try:
        request_data = json.loads(input[0].parts[0].content)
        book_title = request_data['book_title']
        query = request_data['query']
        filename = os.path.join(os.path.dirname(__file__), "data", f"{book_title}.txt")
    except (json.JSONDecodeError, KeyError) as e:
        error_message = f"Invalid input format. Please provide a JSON string with 'book_title' and 'query'. Error: {e}"
        yield Message(parts=[MessagePart(content=error_message)])
        return

    # Validate file exists; provide helpful feedback with detected keys
    if not os.path.isfile(filename):
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        available = []
        if os.path.isdir(data_dir):
            available = [os.path.splitext(f)[0] for f in os.listdir(data_dir) if f.endswith('.txt')]
        yield Message(parts=[MessagePart(content=(
            "Requested book not found: '" + book_title + "'. "
            "Ensure the 'book_title' matches one of: " + ", ".join(available)
        ))])
        return

    # Dynamically create and configure the RAG tool for the requested book
    rag_tool = RagTool(
        config=config,
        chunk_size=1200,
        chunk_overlap=200,
    )
    # Add the local text file to the RAG index. Some versions of crewai_tools expect a
    # positional path argument rather than a named 'file_path'.
    rag_tool.add(filename)

    # Define the CrewAI agent with a generalized role
    archivist = Agent(
        role="Literary Archivist",
        goal=f"Provide accurate, verbatim quotes and summaries from the book '{book_title}'",
        backstory=f"You are a meticulous archivist with a perfect memory of the book '{book_title}'. Your purpose is to retrieve and present information from the text without interpretation or analysis.",
        verbose=True,
        allow_delegation=False,
        llm=llm,
        tools=[rag_tool],
        max_retry_limit=5,
    )

    # Define the task for the agent
    task1 = Task(
        description=query,
        expected_output="A comprehensive, factual answer based on the book's content.",
        agent=archivist,
    )
    crew = Crew(agents=[archivist], tasks=[task1], verbose=True)

    task_output = await crew.kickoff_async()
    yield Message(parts=[MessagePart(content=str(task_output))])


if __name__ == "__main__":
    server.run(port=8001)
