from notion_client import Client
import os
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
notion = Client(auth=NOTION_API_KEY)

# List databases
databases = notion.search(filter={"property": "object", "value": "database"})
for db in databases["results"]:
    print(db["id"], db["title"])

pages = notion.databases.query(
    database_id="abdbe66c-c71f-4531-9d8c-7f97813f99d5",
    filter={
        "property": "Status",
        "status": {
            "equals": "Testing"
        }
    }
)
