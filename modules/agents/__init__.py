from ..tools.notion_tool import fetch_notion_tasks, ft_fetch_notion_tasks
from ..tools.slack_tool import fetch_channel_messages, get_list_of_channels, get_list_of_users
from ..tools.slack_tool import ft_fetch_channel_messages, ft_get_list_of_channels, ft_get_list_of_users
from ..tools.request_tool import get_request_report, ft_get_request_report, get_today_date, summation_tool, ft_get_today_date, ft_summation_tool
from ..config import OPENAI_API_KEY, DEFAULT_MODEL
from ..utils.db_utils import (
    init_db, load_threads_from_db, save_thread_to_db,
    get_history_from_db, cleanup_old_threads, add_message_to_history
)
import openai
import json
import time
import logging
from agents import Agent, ModelSettings, Runner
openai.api_key = OPENAI_API_KEY


class MyAssistant:
    """
    A class representing an OpenAI Assistant configured for Slack and Notion integration.
    """

    def __init__(self):
        self.tools = [
            {"type": "code_interpreter"},
            {
                "type": "function",
                "function": {
                    "name": "get_request_report",
                    "description": "Fetch request report from the API.\nArgs:\n    from_date (str): The start date in YYYY-MM-DD format.\n    to_date (str): The end date in YYYY-MM-DD format.\nReturns:\n    dict: The response from the API.",
                    "strict": True,
                    "parameters": {
                        "properties": {
                            "from_date": {
                                "title": "From Date",
                                "type": "string"
                            },
                            "to_date": {
                                "title": "To Date",
                                "type": "string"
                            }
                        },
                        "required": [
                            "from_date",
                            "to_date"
                        ],
                        "title": "get_request_report_args",
                        "type": "object",
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "summation_tool",
                    "description": "Perform the summation.",
                    "strict": True,
                    "parameters": {
                        "properties": {
                            "array": {
                                "items": {
                                    "type": "integer"
                                },
                                "title": "Array",
                                "type": "array"
                            }
                        },
                        "required": [
                            "array"
                        ],
                        "title": "summation_tool_args",
                        "type": "object",
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_today_date",
                    "description": "Returns today's date in YYYY-MM-DD format.",
                    "strict": True,
                    "parameters": {
                        "properties": {},
                        "title": "get_today_date_args",
                        "type": "object",
                        "additionalProperties": False,
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_notion_tasks",
                    "description": "Fetch tasks from Notion",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_list_of_users",
                    "description": "List Slack users (including user name and ID).",
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
                    "description": "List Slack channels (you can use this to get the channel ID)",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]

        # Create a new assistant
        logging.info("Creating a new assistant")
        self.assistant = openai.beta.assistants.create(
            name="Personal Slack AI Assistant",
            model=DEFAULT_MODEL,
            instructions="""
            You are a helpful assistant that can:
            - analyze data and answer questions regarding number of requests that clients made in a specific range of time.
            - analyze tasks in a Notion database to answer questions or send alert regarding the status of tasks
            Note:
            - If the question is about Request statistics:
                + Do not give answer if the client's name or URI did not match exactly with what you found. In that case, show the user the ambiguity and ask them to provide more information.
                + If you have to make a summation, use the summation tool. NEVER do the summation yourself.
            - If the question is about Notion tasks:
                + If the user explicitly requests to mention Slack users, find the correct Slack ID of the corresponding user in the Notion database and replace the assignees with Slack mention <@USER_ID>.
                + You can map the Slack user to the Notion user using either the name or email field:
                    - Using name: Thang Bui Manh (name in Notion) -> thang b m -> thangbm (name in Slack) or Nguyen Tai Long -> n t long -> longnt.
                    - Using email: thangbm (name in Slack) -> thangbm@kalapa.vn (email in Notion).
                - When being asked about tasks in a specific time range, it includes both tasks that are CREATED or EDITED within that time range.
            
            - Use available tools when needed.
            - Always respond in Vietnamese (but keep some special technical terms such as task, request, user, ... in English).
            - Always provide a complete answer.
            """,
            tools=self.tools
        )

        self.load_user_threads()

    def load_user_threads(self):
        """
        Load user threads from the database.
        """
        init_db()
        cleanup_old_threads()
        self.user_threads = load_threads_from_db()

    async def take_order(self, message, thread_key):
        """
        Take an order from the user and return the assistant's response.

        Args:
            message (str): The user's message.

        Returns:
            str: The assistant's response.
        """
        thread_id = self.user_threads.get(thread_key)
        if not thread_id:
            thread = openai.beta.threads.create()
            thread_id = thread.id
            self.user_threads[thread_key] = thread_id
            # Save new thread to the database
            save_thread_to_db(thread_key, thread_id)

            logging.info(f"Created new thread: {thread_id} for {thread_key}")

        user_id = thread_key.split(":")[0]
        # Call the assistant with the user's message
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=f"User {user_id}: {message}"
        )

        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=self.assistant.id
        )
        while True:
            status = openai.beta.threads.runs.retrieve(
                thread_id=thread_id, run_id=run.id)
            logging.info(f"Run status: {status.status}")
            if status.status == "completed":
                break
            elif status.status == "failed":
                logging.error(
                    f"❌ Run failed. Details: {json.dumps(status.to_dict(), indent=2)}")
                break
            elif status.status == "requires_action":
                tool_outputs = []
                for tool_call in status.required_action.submit_tool_outputs.tool_calls:
                    fn_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)

                    try:
                        logging.info(
                            f"Calling function: {fn_name} with args: {args}")
                        if fn_name == "fetch_notion_tasks":
                            output = fetch_notion_tasks(**args)
                        elif fn_name == "get_list_of_users":
                            output = await get_list_of_users()
                        elif fn_name == "fetch_channel_messages":
                            output = await fetch_channel_messages(**args)
                        elif fn_name == "get_list_of_channels":
                            output = await get_list_of_channels()
                        elif fn_name == "get_request_report":
                            output = get_request_report(**args)
                        elif fn_name == "summation_tool":
                            output = summation_tool(**args)
                        elif fn_name == "get_today_date":
                            output = get_today_date()
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
        return response_text


class MyAgent():
    def __init__(self):
        self.request_monitor_agent = Agent(
            name="Request Monitor Agent",
            instructions="You are a helpful assistant that can analyze data and answer questions regarding number of requests that clients made in a specific range of time.\n"
            "Do not give answer if the client's name or URI did not match exactly with what you found. In that case, show the user the ambiguity and ask them to provide more information.\n"
            "If the question involves a summation, use the summation tool to calculate the result wherever needed. NEVER do the summation yourself.\n"
            "Answer in Vietnamese unless being asked to respond in English.\n"
            "ALWAYS provide a complete and final answer, never just your thinking process.",
            tools=[
                ft_get_request_report, ft_get_today_date, ft_summation_tool
            ],
            model=DEFAULT_MODEL
        )

        self.task_monitor_agent = Agent(
            name="Task Monitor Agent",
            instructions="You are a helpful assistant that can analyze tasks in a Notion database to answer questions or send alert regarding the status of tasks.\n"
            "If requested, find the correct Slack ID of the corresponding user in the Notion database and replace the assignees with Slack mention <@USER_ID>.\n"
            "You can map the Slack user to the Notion user using either the name or email field:\n"
            "- Using name: Thang Bui Manh (name in Notion) -> thang b m -> thangbm (name in Slack) or Nguyen Tai Long -> n t long -> longnt.\n"
            "- Using email: thangbm (name in Slack) -> thangbm@kalapa.vn (email in Notion).\n"
            "When being asked about tasks in a specific time range, it includes both tasks that are CREATED or EDITED within that time range.\n"
            "Answer in Vietnamese unless being asked to respond in English.\n"
            "ALWAYS provide a complete and final answer, never just your thinking process.",
            tools=[
                ft_fetch_notion_tasks,
                ft_get_today_date,
                ft_get_list_of_users
            ],
            model=DEFAULT_MODEL
        )

        self.agent = Agent(
            name="Personal slack assistant",
            instructions=(
                "You are a helpful assistant that can respond to messages in Slack.\n"
                "If being asked about request report, handoff to the request monitor agent.\n"
                "If being asked about tasks, handoff to the task monitor agent.\n"
                "If being asked about anything else, just reply it is out of your scope (respond in a friendly and helpful manner).\n"
                "ALWAYS provide a complete and final answer, never just your thinking process.\n"
                "End your responses with a clear summary or answer to the user's question."
            ),
            handoffs=[self.request_monitor_agent, self.task_monitor_agent],
            model=DEFAULT_MODEL
        )

        self.load_user_threads()

    def load_user_threads(self):
        """
        Load user threads from the database.
        """
        init_db()
        cleanup_old_threads()
        self.user_threads = load_threads_from_db()

    async def take_order(self, message, thread_key):
        """
        Take an order from the user and return the assistant's response.

        Args:
            message (str): The user's message.

        Returns:
            str: The assistant's response.
        """
        if thread_key not in self.user_threads:
            self.user_threads[thread_key] = None
            # Save new thread to the database
            save_thread_to_db(thread_key, None)

            logging.info(f"Created new thread: {thread_key}")

        conversation = get_history_from_db(thread_key)
        history = "\n\n".join(
            [f"{m['role']}:\n{m['content']}" for m in conversation])
        print(f"Conversation history:\n{history}")

        user_id = thread_key.split(":")[0]
        # Call the agent with the user's message
        result = await Runner.run(
            self.agent,
            "Previous conversation:\n\n{}.\n\nReply to the current message from user {}:\n{}".format(
                history, user_id, message)
        )
        # print(result.to_input_list())

        add_message_to_history(thread_key, "user {}".format(user_id), message)
        add_message_to_history(thread_key, "assistant", result.final_output)
        return result.final_output


def create_assistant(type="assistant"):
    """
    Create and return an assistant instance.

    Args:
        type (str): The type of assistant to create. Could be "assistant" or "agent".

    Returns:
        Assistant: An instance of the Assistant class.
    """
    if type == "assistant":
        return MyAssistant()
    elif type == "agent":
        return MyAgent()
    else:
        raise ValueError(f"Unknown assistant type: {type}")
