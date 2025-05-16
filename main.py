import openai
import os
import time
import json
import logging
import openai

from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from fastapi import FastAPI, Request
from modules.utils.db_utils import update_thread_timestamp
from modules.agents import create_assistant
from modules.tools.slack_tool import app
from modules.utils.common import markdown_to_slack
from modules.config import ASSISTANT_TYPE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

fastapi_app = FastAPI()
handler = AsyncSlackRequestHandler(app)

# Store Slack user-thread mapping (in-memory cache)
user_threads = {}

assistant = create_assistant(ASSISTANT_TYPE)

@app.event("message")
async def handle_message(event, say):
    user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text")

    if not user_id or not text:
        return

    thread_key = f"{user_id}:{channel_id}"
    logging.info(f"Received message: {text} (Thread Key: {thread_key})")
    
    response_text = await assistant.take_order(text, thread_key)
    await say(blocks=[
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": markdown_to_slack(response_text)}
        },
        {
            "type": "divider"
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "Made by LongNT's AI assistant"}]
        }
    ])
    
    # Update the thread's last used timestamp in the database
    update_thread_timestamp(thread_key)

@fastapi_app.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)