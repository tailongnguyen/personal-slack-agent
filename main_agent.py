from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from fastapi import FastAPI, Request
from notion_client import Client
from agents import Agent, ModelSettings, function_tool, Runner
from datetime import datetime, timedelta
from dotenv import load_dotenv
from utils import markdown_to_slack
import os
import openai
import logging
# Import database utilities from the new module
from db_utils import init_db, load_threads_from_db, save_thread_to_db, update_thread_timestamp, cleanup_old_threads

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Load environment variables from .env file
load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Initialize OpenAI client
openai.api_key = OPENAI_API_KEY
client_openai = openai.Client(api_key=OPENAI_API_KEY)

notion = Client(auth=NOTION_API_KEY)
app = AsyncApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

fastapi_app = FastAPI()
handler = AsyncSlackRequestHandler(app)

# Use WebClient from the app
client = app.client

# Dictionary to store conversation threads by user and channel (in-memory cache)
conversation_threads = {}

# Initialize the database and load threads on startup
@fastapi_app.on_event("startup")
async def startup_event():
    init_db()
    cleanup_old_threads()
    global conversation_threads
    conversation_threads = load_threads_from_db()

@function_tool
def fetch_notion_tasks(days: int) -> list:
    '''
    Fetch tasks from a Notion database.
    Args:
        days (int): The number of days to look back for tasks.
    Returns:
        list: A list of tasks from the Notion database.
    '''
    print("[Agent used tool] fetch_notion_tasks()")
    pages = notion.databases.query(
        database_id="abdbe66c-c71f-4531-9d8c-7f97813f99d5",
        filter={
            "and": [
                {
                    "or": [
                        {
                            "property": "Status",
                            "status": {
                                "equals": "In progress"
                            }
                        },
                        {
                            "property": "Status",
                            "status": {
                                "equals": "Testing"
                            }
                        },
                        {
                            "property": "Status",
                            "status": {
                                "equals": "Done"
                            }
                        }
                    ]
                },
                {
                    "property": "Sub-tasks",
                    "relation": {
                        "is_empty": True
                    }
                },
                {
                    "property": "Created time",
                    "date": {
                        "on_or_after": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                    }
                }
            ]
        }
    )

    return [{
        "created_time": p.get("created_time"),
        "last_edited_time": p.get("last_edited_time"),
        "title": p.get("properties", {}).get("Task", {}).get("title", [{}])[0].get("text", {}).get("content"),
        "url": p.get("url"),
        "status": p.get("properties", {}).get("Status", {}).get("status", {}).get("name"),
        "assignee": [{
            "name": _p.get("name", "UNKNOWN"),
            "email": _p.get("person", {}).get("email", "UNKNOWN")
        } for _p in p.get("properties", {}).get("Assignee", {}).get("people", [])],
    } for p in pages.get("results", []) if p.get("object") == "page"]

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
    filtered_messages = [{    
        "time": m["ts"],
        "content": m["text"]
    } for m in messages if "text" in m and m["text"].startswith("*REQUEST COUNTER*")]
    print("Filtered messages:", len(filtered_messages))
    return filtered_messages

@function_tool
async def get_list_of_channels() -> list:
    print("[Agent used tool] get_list_of_channels()")
    response = await client.conversations_list(types="public_channel,private_channel")
    channels = response["channels"]
    # print(f"Channels: {channels}")
    return channels

@function_tool
async def get_list_of_users() -> list:
    '''
    Fetch a list of users in the Slack workspace.
    Returns:
        list: A list of users with their IDs and names.
    '''
    response = await client.users_list()
    users = response["members"]
    user_list = [{"id": user["id"], "name": user["name"]} for user in users if not user.get("is_bot") and user.get("id") != "USLACKBOT"]
    return user_list

request_monitor_agent = Agent(
    name="Request Monitor Agent",
    instructions="You are a helpful assistant that can respond to messages in Slack."
                 "Your main task is analyzing messages in a channel called ekyc-monitoring to answer questions regarding number of requests that clients made in a specific range of time."
                 "Do not give answer if the client's name or URI did not match exactly with what you found. In that case, show the user the ambiguity and ask them to provide more information."
                 "Answer in Vietnamese unless being asked to respond in English."
                 "ALWAYS provide a complete and final answer, never just your thinking process.",
    tools=[
        fetch_channel_messages,
        get_list_of_channels,
    ],
    model="gpt-4o"
)

task_monitor_agent = Agent(
    name="Task Monitor Agent",
    instructions="You are a helpful assistant that can respond to messages in Slack."
                 "Your main task is analyzing tasks in a Notion database to answer questions or send alert regarding the status of tasks."
                 "If requested, find the correct Slack ID of the corresponding user in the Notion database and replace the assignees with Slack mention <@USER_ID>."
                 "Common relation between the username in Notion and Slack is like: Thang Bui Manh (name in Notion) -> thang b m -> thangbm (name in Slack) or Nguyen Tai Long -> n t long -> longnt."
                 "Answer in Vietnamese unless being asked to respond in English."
                 "ALWAYS provide a complete and final answer, never just your thinking process.",
    tools=[
        fetch_notion_tasks,
        get_list_of_users
    ],
    model="gpt-4o"
)

my_agent = Agent(
    name="Personal slack assistant",
    instructions=(
        "You are a helpful assistant that can respond to messages in Slack. "
        "If being asked about request repport, handoff to the request monitor agent."
        "If being asked about tasks, handoff to the task monitor agent."
        "If being asked about anything else, just reply it is out of your scope (respond in a friendly and helpful manner)."
        "ALWAYS provide a complete and final answer, never just your thinking process. "
        "End your responses with a clear summary or answer to the user's question."
    ),
    handoffs=[request_monitor_agent, task_monitor_agent],
    model="gpt-4o"
)

async def get_conversation_history(thread_id, limit=10):
    """
    Retrieve conversation history from an OpenAI thread
    
    Args:
        thread_id: The OpenAI thread ID
        limit: Maximum number of messages to retrieve
        
    Returns:
        A string containing the conversation history in a format the agent can understand
    """
    try:
        # Get messages from the thread
        messages = client_openai.beta.threads.messages.list(
            thread_id=thread_id,
            order="desc",  # Get most recent messages first
            limit=limit
        )
        
        # Format messages into a conversation history string
        history = []
        for msg in reversed(list(messages.data)[1:]):  # Process from oldest to newest
            role = "User" if msg.role == "user" else "Assistant"
            content = msg.content[0].text.value if hasattr(msg, 'content') and msg.content else ""
            if role == "User":
                history.append(f"{role}: {content}")
            
        return "\n".join(history)
    except Exception as e:
        print(f"Error retrieving conversation history: {e}")
        return ""

# Listen to all messages
@app.event("message")
async def handle_message(event, say):
    # Ignore messages from the bot itself
    if event.get("subtype") == "bot_message":
        return

    # Get user and channel IDs to track the conversation
    user_id = event.get("user")
    channel_id = event.get("channel")
    thread_key = f"{user_id}:{channel_id}"
    
    # Get OpenAI thread ID or create a new one
    thread_id = conversation_threads.get(thread_key)
    if not thread_id:
        # Create a new thread in OpenAI
        thread = client_openai.beta.threads.create()
        thread_id = thread.id
        conversation_threads[thread_key] = thread_id
        save_thread_to_db(thread_key, thread_id)
        print(f"Created new thread: {thread_id} for {thread_key}")
    
    # Add user message to the OpenAI thread
    prompt = f"{event['text']}"
    print(f"Received message: {prompt} (Thread ID: {thread_id})")
    
    # Add the user message to the thread
    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=prompt
    )
    
    # Get conversation history
    history = await get_conversation_history(thread_id)
    
    # Augment the prompt with conversation history if available
    enhanced_prompt = prompt
    if history:
        enhanced_prompt = f"""Previous conversation:\n{history}\nCurrent message: {prompt}\nPlease respond to the current message in the context of our conversation."""
        print(f"Enhanced prompt:\n{enhanced_prompt}")
    
    # Process the message with your agent
    result = await Runner.run(
        my_agent, 
        enhanced_prompt
    )
    
    # Add the assistant's response to the thread for continuity
    client_openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="assistant",
        content=result.final_output
    )
    
    await say(blocks=[
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": markdown_to_slack(result.final_output)}
        },
        {
            "type": "divider"
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "Made by LongNT's AI assistant"}]
        }
    ])
    update_thread_timestamp(thread_key)

@fastapi_app.get("/threads")
async def check_threads(req: Request):
    return list(conversation_threads.keys())

@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)

@fastapi_app.get("/cleanup-threads/{days}")
async def cleanup_threads_endpoint(days: int = 30):
    """API endpoint to manually trigger cleanup of old threads"""
    deleted_count = cleanup_old_threads(days)
    # Also update the in-memory dictionary
    global conversation_threads
    conversation_threads = load_threads_from_db()
    return {"message": f"Cleaned up {deleted_count} old conversation threads"}