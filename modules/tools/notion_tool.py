from ..config import NOTION_API_KEY, NOTION_DATABASE_ID
from notion_client import Client
from datetime import datetime, timedelta
from agents import function_tool
import logging


notion = Client(auth=NOTION_API_KEY)

@function_tool
def ft_fetch_notion_tasks() -> list:
    '''
    Fetch tasks from Notion.
    Args:
        None
    Returns:
        list: A list of tasks with their details.
    '''
    logging.info("[Tool] fetch_notion_tasks")
    return fetch_notion_tasks()

def fetch_notion_tasks() -> list:
    pages = notion.databases.query(
        database_id=NOTION_DATABASE_ID,
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
                        "on_or_after": (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
                    }
                }
            ]
        }
    )

    return [{
        "created_time": p.get("created_time"),
        "last_edited_time": p.get("last_edited_time"),
        "is_active": p.get("created_time") > (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d") or p.get("last_edited_time") > (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
        "title": p.get("properties", {}).get("Task", {}).get("title", [{}])[0].get("text", {}).get("content"),
        "url": p.get("url"),
        "status": p.get("properties", {}).get("Status", {}).get("status", {}).get("name"),
        "assignee": [{
            "name": _p.get("name", "UNKNOWN"),
            "email": _p.get("person", {}).get("email", "UNKNOWN")
        } for _p in p.get("properties", {}).get("Assignee", {}).get("people", [])],
    } for p in pages.get("results", []) if p.get("object") == "page"]