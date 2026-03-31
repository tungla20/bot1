"""Report Agent — orchestrates Gemini ↔ ERP API for report generation.

Manages multi-turn conversation state and executes ERP function calls
as directed by the Gemini model.
"""

import json
import logging
from datetime import date
from typing import Any, Dict, Optional

import google.generativeai as genai

from bot.ai.gemini_client import create_chat_session
from bot.erp_client import ERPClient, AuthenticationError, APIError

logger = logging.getLogger(__name__)


class ReportAgent:
    """Per-user report agent that manages a Gemini chat and ERP calls."""

    def __init__(self, erp_client: ERPClient):
        self.erp_client = erp_client
        today = date.today().isoformat()
        self.chat = create_chat_session(today)

    async def process_message(self, user_message: str) -> str:
        """Process a user message and return the bot's response.

        This may involve:
        1. Sending the message to Gemini
        2. If Gemini returns function calls → execute them against ERP
        3. Send results back to Gemini
        4. Return the final text response

        Args:
            user_message: The user's natural language message.

        Returns:
            The formatted report or clarifying question.
        """
        try:
            # Send user message to Gemini
            response = await self._send_to_gemini(user_message)

            # Process function calls in a loop (Gemini may chain multiple calls)
            max_rounds = 5  # Safety limit
            rounds = 0

            while rounds < max_rounds:
                rounds += 1

                # Check if the response contains function calls
                function_calls = self._extract_function_calls(response)

                if not function_calls:
                    # No function calls — return the text response
                    return self._extract_text(response)

                # Execute all function calls
                function_responses = []
                for fc in function_calls:
                    result = await self._execute_function(fc.name, dict(fc.args))
                    function_responses.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=fc.name,
                                response={"result": result},
                            )
                        )
                    )

                # Send function results back to Gemini
                response = await self._send_function_results(function_responses)

            return self._extract_text(response)

        except AuthenticationError as e:
            return f"⚠️ {e}"
        except APIError as e:
            return f"❌ Lỗi API: {e}"
        except Exception as e:
            logger.error("Report agent error: %s", e, exc_info=True)
            return (
                "❌ Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại.\n\n"
                f"<i>Chi tiết: {e}</i>"
            )

    async def _send_to_gemini(self, message: str) -> genai.types.GenerateContentResponse:
        """Send a text message to Gemini."""
        return self.chat.send_message(message)

    async def _send_function_results(
        self, parts: list[genai.protos.Part]
    ) -> genai.types.GenerateContentResponse:
        """Send function results back to Gemini."""
        return self.chat.send_message(parts)

    def _extract_function_calls(
        self, response: genai.types.GenerateContentResponse
    ) -> list:
        """Extract function calls from a Gemini response."""
        calls = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.function_call and part.function_call.name:
                    calls.append(part.function_call)
        return calls

    def _extract_text(self, response: genai.types.GenerateContentResponse) -> str:
        """Extract the text content from a Gemini response."""
        parts = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.text:
                    parts.append(part.text)
        return "\n".join(parts) if parts else "🤔 Không có phản hồi từ AI."

    async def _execute_function(self, name: str, args: Dict[str, Any]) -> Any:
        """Execute an ERP function and return the result.

        Args:
            name: The function name from the Gemini tool call.
            args: The function arguments.

        Returns:
            The API response data (serializable).
        """
        logger.info("Executing function: %s(%s)", name, args)

        try:
            if name == "get_time_applications":
                return await self._get_time_applications(args)
            elif name == "get_my_applications":
                return await self._get_my_applications(args)
            elif name == "get_employees":
                return await self._get_employees(args)
            elif name == "get_pending_approvals":
                return await self._get_pending_approvals(args)
            else:
                return {"error": f"Unknown function: {name}"}
        except Exception as e:
            logger.error("Function %s failed: %s", name, e)
            return {"error": str(e)}

    async def _get_time_applications(self, args: Dict[str, Any]) -> Any:
        """Fetch time applications with filters."""
        params = {}
        if args.get("status"):
            params["status"] = args["status"]
        if args.get("type"):
            params["type"] = args["type"]
        if args.get("from_date"):
            params["fromDate"] = args["from_date"]
        if args.get("to_date"):
            params["toDate"] = args["to_date"]
        params["page"] = args.get("page", 1)
        params["limit"] = args.get("limit", 20)
        params["sortOrder"] = "desc"

        resp = await self.erp_client._request(
            "GET",
            "/api/application/time-applications",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    async def _get_my_applications(self, args: Dict[str, Any]) -> Any:
        """Fetch the current user's applications."""
        params = {}
        if args.get("status"):
            params["status"] = args["status"]
        if args.get("type"):
            params["type"] = args["type"]
        params["page"] = args.get("page", 1)
        params["limit"] = args.get("limit", 20)
        params["sortOrder"] = "desc"

        return await self.erp_client.get_my_applications(**params)

    async def _get_employees(self, args: Dict[str, Any]) -> Any:
        """Fetch employees."""
        return await self.erp_client.get_employees(
            search=args.get("search", ""),
            page=args.get("page", 1),
            limit=args.get("limit", 20),
        )

    async def _get_pending_approvals(self, args: Dict[str, Any]) -> Any:
        """Fetch pending approvals."""
        return await self.erp_client.get_pending_approvals(
            page=args.get("page", 1),
            limit=args.get("limit", 20),
        )
