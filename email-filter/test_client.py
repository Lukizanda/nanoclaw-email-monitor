"""Quick end-to-end test of the classify_emails MCP tool over SSE."""
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

SAMPLES = [
    {"sender": "billing@acme.com", "subject": "Invoice #1042 overdue — action required",
     "body_preview": "Dear Alex, your invoice of $450 is now 14 days overdue. Please pay to avoid late fees."},
    {"sender": "news@medium.com", "subject": "Your weekly digest",
     "body_preview": "Top stories this week in technology and design. Read more on Medium."},
    {"sender": "recruiter@bigco.com", "subject": "Interview invitation — Senior Engineer",
     "body_preview": "Hi Alex, we'd love to schedule an interview next week. Are you available Tuesday?"},
    {"sender": "deals@shop.com", "subject": "FLASH SALE 50% off everything!",
     "body_preview": "Limited time only! Shop now and save big on all items."},
]


async def main():
    async with sse_client("http://localhost:8765/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools])
            result = await session.call_tool("classify_emails", {"emails": SAMPLES})
            print("\n--- classify_emails result ---")
            for block in result.content:
                print(getattr(block, "text", block))


asyncio.run(main())
