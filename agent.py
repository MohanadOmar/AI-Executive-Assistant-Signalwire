import json
import os
from collections import defaultdict
from openai import OpenAI
from tools import (
    get_emails, create_draft, send_email, reply_to_email, add_label,
    get_calendar_events, create_calendar_event,
    get_notion_tasks, update_notion_task, create_notion_task,
    send_sms, search_knowledge_base,
    search_contacts, create_contact, update_contact,
    list_recent_docs, read_doc, create_doc, append_to_doc,
    list_recent_sheets, read_sheet, create_sheet, append_row, update_cell,
)

MODEL = "gpt-4o-mini"

# ─── Tool definitions ────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_emails",
            "description": "Read emails from Mohanad's Gmail inbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Max emails to return (default 5)"},
                    "query": {"type": "string", "description": "Gmail search query (default: is:unread)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft",
            "description": "Create an email draft. Use for 'draft', 'write', 'compose' — never for 'send'.",
            "parameters": {
                "type": "object",
                "required": ["to", "subject", "body"],
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email. ONLY use when user explicitly says 'send'.",
            "parameters": {
                "type": "object",
                "required": ["to", "subject", "body"],
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reply_to_email",
            "description": "Reply to an existing email thread. Requires the original message ID.",
            "parameters": {
                "type": "object",
                "required": ["message_id", "body"],
                "properties": {
                    "message_id": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_label",
            "description": "Add a label to a Gmail message.",
            "parameters": {
                "type": "object",
                "required": ["message_id", "label_name"],
                "properties": {
                    "message_id": {"type": "string"},
                    "label_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get upcoming events from Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {"type": "string", "description": "ISO datetime start"},
                    "time_max": {"type": "string", "description": "ISO datetime end"},
                    "max_results": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Create a new Google Calendar event.",
            "parameters": {
                "type": "object",
                "required": ["title", "start"],
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime"},
                    "end": {"type": "string", "description": "ISO datetime (default: 30 min after start)"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_notion_tasks",
            "description": "Get tasks from the EG23 Notion database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "return_all": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_notion_task",
            "description": "Update an existing Notion task. Requires page ID.",
            "parameters": {
                "type": "object",
                "required": ["page_id"],
                "properties": {
                    "page_id": {"type": "string"},
                    "status": {"type": "string"},
                    "title": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_notion_task",
            "description": "Create a new task in Notion.",
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_sms",
            "description": "Send an SMS via SignalWire.",
            "parameters": {
                "type": "object",
                "required": ["to", "message"],
                "properties": {
                    "to": {"type": "string", "description": "Phone number in E.164 format"},
                    "message": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search EG23's internal knowledge base in Supabase.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                },
            },
        },
    },
    # ─── Google Contacts ───────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Search Google Contacts by name, email, or phone. Use this when the user mentions a person by name and you need their contact info.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Name, email, or phone fragment"},
                    "max_results": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_contact",
            "description": "Add a new contact to Google Contacts.",
            "parameters": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "company": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_contact",
            "description": "Update an existing contact's email or phone. Get resource_name from search_contacts first.",
            "parameters": {
                "type": "object",
                "required": ["resource_name"],
                "properties": {
                    "resource_name": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                },
            },
        },
    },
    # ─── Google Docs ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "list_recent_docs",
            "description": "List recent Google Docs, optionally filtered by name keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer"},
                    "query": {"type": "string", "description": "Filter docs by name keyword"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": "Read the full text content of a Google Doc. Get the doc_id from list_recent_docs.",
            "parameters": {
                "type": "object",
                "required": ["doc_id"],
                "properties": {
                    "doc_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_doc",
            "description": "Create a new Google Doc with optional initial content.",
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_to_doc",
            "description": "Append text to the end of a Google Doc.",
            "parameters": {
                "type": "object",
                "required": ["doc_id", "text"],
                "properties": {
                    "doc_id": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
    },
    # ─── Google Sheets ─────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "list_recent_sheets",
            "description": "List recent Google Sheets, optionally filtered by name keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer"},
                    "query": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_sheet",
            "description": "Read data from a Google Sheet. Returns headers + rows. Get sheet_id from list_recent_sheets.",
            "parameters": {
                "type": "object",
                "required": ["sheet_id"],
                "properties": {
                    "sheet_id": {"type": "string"},
                    "range_name": {"type": "string", "description": "A1 notation like 'Sheet1!A1:E20'. Default is first sheet A1:Z100."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_sheet",
            "description": "Create a new Google Sheet with optional column headers.",
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                    "headers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Column headers for row 1",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_row",
            "description": "Append a row to a Google Sheet.",
            "parameters": {
                "type": "object",
                "required": ["sheet_id", "values"],
                "properties": {
                    "sheet_id": {"type": "string"},
                    "values": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Cell values left-to-right",
                    },
                    "sheet_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_cell",
            "description": "Update a single cell in a Google Sheet (e.g. mark deal status, change a value).",
            "parameters": {
                "type": "object",
                "required": ["sheet_id", "cell", "value"],
                "properties": {
                    "sheet_id": {"type": "string"},
                    "cell": {"type": "string", "description": "A1 notation like 'B5'"},
                    "value": {"type": "string"},
                    "sheet_name": {"type": "string"},
                },
            },
        },
    },
]

TOOL_MAP = {
    "get_emails": get_emails,
    "create_draft": create_draft,
    "send_email": send_email,
    "reply_to_email": reply_to_email,
    "add_label": add_label,
    "get_calendar_events": get_calendar_events,
    "create_calendar_event": create_calendar_event,
    "get_notion_tasks": get_notion_tasks,
    "update_notion_task": update_notion_task,
    "create_notion_task": create_notion_task,
    "send_sms": send_sms,
    "search_knowledge_base": search_knowledge_base,
    "search_contacts": search_contacts,
    "create_contact": create_contact,
    "update_contact": update_contact,
    "list_recent_docs": list_recent_docs,
    "read_doc": read_doc,
    "create_doc": create_doc,
    "append_to_doc": append_to_doc,
    "list_recent_sheets": list_recent_sheets,
    "read_sheet": read_sheet,
    "create_sheet": create_sheet,
    "append_row": append_row,
    "update_cell": update_cell,
}

# ─── In-memory session store (keyed by phone number) ─────────────────────────

_sessions: dict[str, list] = defaultdict(list)
MAX_HISTORY = 20


def run_agent(user_message: str, system_prompt: str, phone_number: str = None, tools: list = None) -> str:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    history = _sessions[phone_number] if phone_number else []

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_message},
    ]

    active_tools = TOOLS if tools is None else tools

    while True:
        kwargs = {"model": MODEL, "messages": messages}
        if active_tools:
            kwargs["tools"] = active_tools
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        assistant_msg = response.choices[0].message
        messages.append(assistant_msg)

        if not assistant_msg.tool_calls:
            break

        for tool_call in assistant_msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            print(f"[Tool] {name}({args})")

            try:
                fn = TOOL_MAP.get(name)
                if not fn:
                    raise ValueError(f"Unknown tool: {name}")
                result = fn(**args)
            except Exception as e:
                result = {"error": str(e)}
                print(f"[Tool Error] {name}: {e}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })

    output = assistant_msg.content or ""

    # Save to session memory
    if phone_number:
        session = _sessions[phone_number]
        session.append({"role": "user", "content": user_message})
        session.append({"role": "assistant", "content": output})
        if len(session) > MAX_HISTORY:
            _sessions[phone_number] = session[-MAX_HISTORY:]

    return output
