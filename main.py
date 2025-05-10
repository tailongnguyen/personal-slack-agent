from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from fastapi import FastAPI, Request
from agents import Agent, ModelSettings, function_tool, Runner
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

app = AsyncApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
fastapi_app = FastAPI()
handler = AsyncSlackRequestHandler(app)

# Use WebClient from the app
client = app.client

@function_tool
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

    messages = response["messages"]
    return [{
        "time": m["ts"],
        "content": m["text"]
    } for m in messages if "text" in m and m["text"].startswith("*REQUEST COUNTER*")]

@function_tool
async def get_list_of_channels() -> list:
    print("[Agent used tool] get_list_of_channels()")
    response = await client.conversations_list(types="public_channel,private_channel")
    channels = response["channels"]
    print(f"Channels: {channels}")
    return channels

agent = Agent(
    name="Personal Slack Assistant",
    instructions="You are a helpful assistant that can summarize and respond to messages in Slack. "
                 "Your main task is analyzing messages in a channel called ekyc-monitoring to answer questions regarding number of requests that clients made in a specific range of time. ",               
    tools=[
        fetch_channel_messages,
        get_list_of_channels,
    ],
    model="gpt-4o"
)

# Listen to all messages
@app.event("message")
async def handle_message(event, say):
    # Ignore messages from the bot itself
    if event.get("subtype") == "bot_message":
        return

    # Process the message
    prompt = f"{event['text']}"
    print(f"Received message: {prompt}")
    result = await Runner.run(agent, prompt)
    await say(result.final_output)

# # Respond to mentions
# @app.event("app_mention")
# def reply_to_mention(event, say):
#     prompt = f"Summarize and respond to this message: {event['text']}"
#     response = query_gpt(prompt)
#     say(response)

@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)