from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
import asyncio
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

app = AsyncApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
# Use WebClient from the app
client = app.client

async def fetch_channel_messages(channel_id: str, limit: int, days: int) -> list:
    '''
    Fetch messages from a Slack channel.
    Args:
        channel_id (str): The ID of the channel to fetch messages from.
        limit (int): The maximum number of messages to fetch.
        days (int): The number of days to look back for messages.
    Returns:
        list: A list of messages from the channel.
    '''
    print("[Agent used tool] fetch_channel_messages()")
    response = await client.conversations_history(
        channel=channel_id,
        limit=limit,
        oldest=int((datetime.now() - timedelta(days=days)).timestamp()),
    )

    res = response["messages"]
    messages = [{
        "time": m["ts"],
        "content": m["text"]
    } for m in res if "text" in m and m["text"].startswith("*REQUEST COUNTER*") and "ekyc-api-prod" in m["text"]]
    print(messages)
    return messages
    
async def get_list_of_channels() -> list:
    response = await client.conversations_list(types="public_channel,private_channel")
    channels = response["channels"]
    print([[c["name"], c["id"]] for c in channels])

# ✅ Correct way to call it
# asyncio.run(get_list_of_channels())
asyncio.run(fetch_channel_messages("C07M57EL9T3", 10, 7))