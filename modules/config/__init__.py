from dotenv import load_dotenv
import os

load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
NOTION_DATABASE_ID = "abdbe66c-c71f-4531-9d8c-7f97813f99d5"
DEFAULT_MODEL = "gpt-4o"
ASSISTANT_TYPE = os.environ.get("ASSISTANT_TYPE", "agent")
THREAD_EXPIRATION_DAYS = 30
THREAD_DATABASE_PATH = "conversation_threads.db"