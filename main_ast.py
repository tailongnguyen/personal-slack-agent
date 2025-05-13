import openai
import os
import time
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from notion_client import Client
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from fastapi import FastAPI, Request
# Import database utilities
from db_utils import init_db, load_threads_from_db, save_thread_to_db, update_thread_timestamp, cleanup_old_threads
from utils import markdown_to_slack

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

openai.api_key = os.environ["OPENAI_API_KEY"]
notion = Client(auth=os.environ["NOTION_API_KEY"])
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

app = AsyncApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
fastapi_app = FastAPI()
handler = AsyncSlackRequestHandler(app)

# Use WebClient from the app
client = app.client

# Store Slack user-thread mapping (in-memory cache)
user_threads = {}

# Initialize database and load threads on startup
@fastapi_app.on_event("startup")
async def startup_event():
    init_db()
    cleanup_old_threads()
    global user_threads
    user_threads = load_threads_from_db()
    logging.info(f"Loaded {len(user_threads)} conversation threads from database")

# ----------------------------
# TOOL FUNCTION DEFINITIONS
# ----------------------------

def fetch_notion_tasks(days: int) -> list:
    print("[Tool] fetch_notion_tasks")
    pages = notion.databases.query(
        database_id="abdbe66c-c71f-4531-9d8c-7f97813f99d5",
        filter={
            "and": [
                {
                    "or": [
                        {"property": "Status", "status": {"equals": s}}
                        for s in ["In progress", "Testing", "Done"]
                    ]
                },
                {"property": "Sub-tasks", "relation": {"is_empty": True}},
                {
                    "property": "Created time",
                    "date": {
                        "on_or_after": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                    }
                }
            ]
        }
    )

    return [
        {
            "created_time": p.get("created_time"),
            "title": p["properties"]["Task"]["title"][0]["text"]["content"],
            "url": p.get("url"),
            "status": p["properties"]["Status"]["status"]["name"]
        }
        for p in pages["results"]
    ]

async def get_list_of_users() -> list:
    print("[Tool] get_list_of_users")
    response = await client.users_list()
    users = response["members"]
    user_list = [{"id": user["id"], "name": user["name"]} for user in users if not user.get("is_bot") and user.get("id") != "USLACKBOT"]
    return user_list    

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
    print("[Tool] fetch_channel_messages()")
    response = await client.conversations_history(
        channel=channel_id,
        limit=limit,
        oldest=int((datetime.now() - timedelta(days=days)).timestamp()),
    )

    messages = response["messages"]
    filtered_messages = [{    
        "time": m["ts"],
        "content": m["text"]
    } for m in messages if "text" in m and m["text"].startswith("*REQUEST COUNTER*")]
    print("Filtered messages:", len(filtered_messages))
    return filtered_messages

async def get_list_of_channels() -> list:
    print("[Tool] get_list_of_channels()")
    response = await client.conversations_list(types="public_channel,private_channel")
    channels = response["channels"]
    # print(f"Channels: {channels}")
    return channels

# ----------------------------
# TOOLS SCHEMA
# ----------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "fetch_notion_tasks",
            "description": "Fetch tasks from Notion in the last N days",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer"}
                },
                "required": ["days"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_list_of_users",
            "description": "List Slack users",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_channel_messages",
            "description": "Fetch messages from a Slack channel in the last N days",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string"},
                    "limit": {"type": "integer"},
                    "days": {"type": "integer"}
                },
                "required": ["channel_id", "limit", "days"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_list_of_channels",
            "description": "List Slack channels",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

assistant = openai.beta.assistants.create(
    name="Slack + Notion Assistant",
    model="gpt-4o",
    instructions="""
You are a helpful assistant that answers questions about:
- Request statistics from a Slack channel called ekyc-monitoring
- Tasks from Notion
Use available tools when needed.
Always respond in Vietnamese (but keep some special technical terms such as task, request, user, ... in English).
Always provide a complete answer.
""",
    tools=tools
)

@app.event("message")
async def handle_message(event, say):
    user_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text")

    if not user_id or not text:
        return

    thread_key = f"{user_id}:{channel_id}"
    thread_id = user_threads.get(thread_key)
    if not thread_id:
        thread = openai.beta.threads.create()
        thread_id = thread.id
        user_threads[thread_key] = thread_id
        # Save new thread to the database
        save_thread_to_db(thread_key, thread_id)
        logging.info(f"Created new thread: {thread_id} for {thread_key}")

    logging.info(f"Received message: {text} (Thread ID: {thread_id})")
    
    openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=f"[User ID: {user_id}] {text}"
    )

    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant.id
    )

    while True:
        status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        # print(f"Run status: {status.status}")
        if status.status == "completed":
            break
        elif status.status == "requires_action":
            tool_outputs = []
            for tool_call in status.required_action.submit_tool_outputs.tool_calls:
                fn_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                try:
                    if fn_name == "fetch_notion_tasks":
                        output = fetch_notion_tasks(**args)
                    elif fn_name == "get_list_of_users":
                        output = await get_list_of_users()
                    elif fn_name == "fetch_channel_messages":
                        output = await fetch_channel_messages(**args)
                    elif fn_name == "get_list_of_channels":
                        output = await get_list_of_channels()
                    else:
                        output = {"error": "Unknown function"}
                except Exception as e:
                    logging.error(f"Error calling function {fn_name}: {e}")
                    output = {"error": str(e)}    

                tool_outputs.append({
                    "tool_call_id": tool_call.id,
                    "output": json.dumps(output)
                })

            openai.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs
            )
        else:
            time.sleep(1)

    messages = openai.beta.threads.messages.list(thread_id=thread_id)
    reply = next((m for m in messages.data if m.role == "assistant"), None)
    response_text = reply.content[0].text.value if reply else "Không có phản hồi từ trợ lý."

    await say(markdown_to_slack(response_text))
    
    # Update the thread's last used timestamp in the database
    update_thread_timestamp(thread_key)

@fastapi_app.post("/slack/events")
async def endpoint(req: Request):
    return await handler.handle(req)
