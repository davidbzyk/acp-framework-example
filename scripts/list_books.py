import asyncio
from acp_sdk.client import Client
from acp_sdk.models import Message, MessagePart


async def main():
    async with Client(base_url="http://127.0.0.1:8002") as client:
        run = await client.run_sync(
            agent="literary_critic_agent",
            input=[Message(parts=[MessagePart(content="List the available books.")])],
        )
        if run.output and run.output[0].parts:
            print(run.output[0].parts[0].content)
        elif run.error:
            print("ERROR:", run.error)
        else:
            print("EMPTY RESPONSE")


if __name__ == "__main__":
    asyncio.run(main())
