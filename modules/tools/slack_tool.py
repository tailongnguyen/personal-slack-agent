from ..config import SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
from slack_bolt.async_app import AsyncApp
from datetime import datetime, timedelta
from agents import function_tool
import logging

app = AsyncApp(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
# Use WebClient from the app
client = app.client

@function_tool
async def ft_get_list_of_users() -> list:
    '''
    Fetch a list of users in the Slack workspace.
    Returns:
        list: A list of users with their IDs and names.
    '''
    logging.info("[Tool] get_list_of_users")
    return await get_list_of_users()

async def get_list_of_users() -> list:
    response = await client.users_list()
    users = response["members"]
    user_list = [{"id": user["id"], "name": user["name"]} for user in users if not user.get("is_bot") and user.get("id") != "USLACKBOT"]
    # print(f"Users: {user_list}")
    return user_list    

@function_tool
async def ft_fetch_channel_messages(channel_id: str, limit: int, days: int) -> list:
    '''
    Fetch messages from a Slack channel.
    Args:
        channel_id (str): The ID of the channel to fetch messages from.
        limit (int): The maximum number of messages to fetch.
        days (int): The number of days to look back for messages.
    Returns:
        list: A list of messages from the channel.
    '''
    logging.info("[Tool] fetch_channel_messages({}, {}, {})".format(channel_id, limit, days))
    return await fetch_channel_messages(channel_id, limit, days)
    
async def fetch_channel_messages(channel_id: str, limit: int, days: int) -> list:
    response = await client.conversations_history(
        channel=channel_id,
        limit=limit,
        oldest=int((datetime.now() - timedelta(days=days)).timestamp()),
    )

    messages = response["messages"]
    # filtered_messages = [{    
    #     "time": m["ts"],
    #     "content": m["text"]
    # } for m in messages if "text" in m and m["text"].startswith("*REQUEST COUNTER*")]
    # logging.info("Filtered messages: %d", len(filtered_messages))
    # return filtered_messages
    return messages

@function_tool
async def ft_get_list_of_channels() -> list:
    '''
    Fetch a list of channels in the Slack workspace.
    Returns:
        list: A list of channels with their IDs and names.
    '''
    logging.info("[Tool] get_list_of_channels")
    return await get_list_of_channels()

async def get_list_of_channels() -> list:
    response = await client.conversations_list(types="public_channel,private_channel")
    channels = response["channels"]
    # logging.info(f"Channels: {channels}")
    return channels
