"""Gemini AI client — wraps google-generativeai for the report agent."""

import logging
from typing import Optional

import google.generativeai as genai

from bot.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# ── Tool definitions (ERP functions the model can call) ──────────────────────

ERP_TOOLS = [
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="get_time_applications",
                description=(
                    "Fetch time applications (leave, overtime, business trip, check-in) "
                    "with optional filters. Returns a paginated list of applications. "
                    "Use this to generate reports about applications, attendance, "
                    "leave usage, overtime stats, etc."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "status": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Filter by status: PENDING, IN_PROGRESS, APPROVED, REJECTED, COMPLETED, CANCELLED",
                        ),
                        "type": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Filter by application type: LEAVE, OVERTIME, BUSINESS_TRIP, CHECKIN",
                        ),
                        "from_date": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Filter start date (ISO format YYYY-MM-DD)",
                        ),
                        "to_date": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Filter end date (ISO format YYYY-MM-DD)",
                        ),
                        "page": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Page number (default 1)",
                        ),
                        "limit": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Items per page (default 20, max 100)",
                        ),
                    },
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="get_my_applications",
                description=(
                    "Fetch the current user's own time applications with optional filters. "
                    "Use this when the user asks about THEIR OWN applications."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "status": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Filter by status: PENDING, IN_PROGRESS, APPROVED, REJECTED, COMPLETED, CANCELLED",
                        ),
                        "type": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Filter by type: LEAVE, OVERTIME, BUSINESS_TRIP, CHECKIN",
                        ),
                        "page": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Page number (default 1)",
                        ),
                        "limit": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Items per page (default 20, max 100)",
                        ),
                    },
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="get_employees",
                description=(
                    "Search and list employees in the ERP system. "
                    "Use this for reports about headcount, employee lookup, etc."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "search": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Search query (name, email, employee code)",
                        ),
                        "page": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Page number (default 1)",
                        ),
                        "limit": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Items per page (default 20, max 100)",
                        ),
                    },
                ),
            ),
            genai.protos.FunctionDeclaration(
                name="get_pending_approvals",
                description=(
                    "Fetch applications waiting for the current user's approval. "
                    "Use for reports on approval workload, bottleneck analysis."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "page": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Page number (default 1)",
                        ),
                        "limit": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Items per page (default 20, max 100)",
                        ),
                    },
                ),
            ),
        ]
    )
]

# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are B.E.A.R Report Agent — an AI assistant inside the B.E.A.R BOT \
(Back-office Efficiency Agent & Ranking) for Twendee ERP.

Your role is to help users generate reports by understanding their natural \
language requests and fetching data from the ERP system.

## Guidelines:
1. If the user's request is unclear or ambiguous, ask a SHORT clarifying \
question. Do NOT guess — ask.
2. When you have enough information, call the appropriate ERP function(s) to \
fetch data.
3. After receiving data, format a clear, well-structured report using emoji \
and simple formatting suitable for Telegram (HTML tags: <b>, <i>, <code>).
4. Keep reports concise but informative. Use bullet points and tables where \
appropriate.
5. If no data is found, say so clearly and suggest alternative queries.
6. Always respond in the SAME LANGUAGE the user uses (Vietnamese or English).
7. Today's date is {today}. Use this to interpret relative date references \
like "this month", "last week", etc.
8. For date ranges, convert to ISO format (YYYY-MM-DD) when calling functions.
9. You can call multiple functions in sequence to compile a comprehensive report.
10. If the data is paginated and there might be more results, mention it and \
offer to fetch the next page.

## Available data:
- Time applications: leave, overtime, business trips, check-in records
- Employees: name, email, employee code, status
- Pending approvals: applications waiting for review

You do NOT have access to: projects, financial data, salary information, or \
system configuration.
"""


def _configure():
    """Configure the Gemini API with the key."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set! Check your .env file.")
    genai.configure(api_key=GEMINI_API_KEY)


def create_chat_session(today: str) -> genai.ChatSession:
    """Create a new Gemini chat session with tools and system prompt.

    Args:
        today: Today's date in YYYY-MM-DD format for context.

    Returns:
        A ChatSession ready for multi-turn conversation.
    """
    _configure()

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        tools=ERP_TOOLS,
        system_instruction=SYSTEM_PROMPT.format(today=today),
    )

    return model.start_chat(enable_automatic_function_calling=False)
