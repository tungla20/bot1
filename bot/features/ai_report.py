"""Feature: AI-powered report generation via natural language.

Provides a /report command that starts a conversation with the Gemini-powered
report agent. Users describe what they need in natural language, and the agent
fetches data from ERP and formats a report.
"""

import logging

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot import database
from bot.erp_client import ERPClient
from bot.ai.report_agent import ReportAgent
from bot.config import REPORT_WAITING_INPUT
from bot.utils.keyboards import back_to_menu_keyboard

logger = logging.getLogger(__name__)

# ── Max message length for Telegram ──────────────────────────────────────────
MAX_TG_MESSAGE = 4096


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /report — start the AI report conversation."""
    chat_id = update.effective_chat.id
    session = await database.get_session(chat_id)

    if session is None:
        await update.effective_message.reply_text(
            "⚠️ Bạn chưa đăng nhập.\nDùng /login để đăng nhập.",
            reply_markup=back_to_menu_keyboard(),
        )
        return ConversationHandler.END

    # Create a fresh report agent for this conversation
    erp_client = ERPClient(chat_id)
    agent = ReportAgent(erp_client)
    context.user_data["report_agent"] = agent

    await update.message.reply_text(
        "🤖 <b>B.E.A.R Report Agent</b>\n\n"
        "Tôi có thể giúp bạn tạo báo cáo từ dữ liệu ERP. "
        "Hãy mô tả báo cáo bạn cần bằng ngôn ngữ tự nhiên.\n\n"
        "<i>Ví dụ:</i>\n"
        '• "Thống kê đơn nghỉ phép tháng này"\n'
        '• "Show me overtime requests for March 2026"\n'
        '• "Danh sách đơn chờ duyệt của tôi"\n\n'
        "Gửi /cancel để thoát.",
        parse_mode="HTML",
    )
    return REPORT_WAITING_INPUT


async def report_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user messages during the report conversation."""
    agent: ReportAgent = context.user_data.get("report_agent")

    if agent is None:
        await update.message.reply_text(
            "⚠️ Phiên báo cáo đã hết. Dùng /report để bắt đầu lại."
        )
        return ConversationHandler.END

    user_message = update.message.text.strip()
    if not user_message:
        return REPORT_WAITING_INPUT

    # Show typing indicator
    await update.effective_chat.send_action("typing")

    # Process through the AI agent
    response = await agent.process_message(user_message)

    # Send response (split if too long)
    await _send_long_message(update, response)

    # Stay in conversation for follow-up questions
    return REPORT_WAITING_INPUT


async def report_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the report conversation."""
    context.user_data.pop("report_agent", None)
    await update.message.reply_text(
        "👋 Đã thoát chế độ báo cáo.",
        reply_markup=back_to_menu_keyboard(),
    )
    return ConversationHandler.END


def build_report_handler() -> ConversationHandler:
    """Build the report ConversationHandler."""
    return ConversationHandler(
        entry_points=[CommandHandler("report", report_command)],
        states={
            REPORT_WAITING_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, report_message),
            ],
        },
        fallbacks=[CommandHandler("cancel", report_cancel)],
        allow_reentry=True,
    )


async def _send_long_message(update: Update, text: str) -> None:
    """Send a message, splitting it if it exceeds Telegram's limit."""
    if len(text) <= MAX_TG_MESSAGE:
        await update.message.reply_text(text, parse_mode="HTML")
        return

    # Split on newlines, respecting the max length
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_TG_MESSAGE:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)

    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="HTML")
        except Exception:
            # Fall back to plain text if HTML parsing fails
            await update.message.reply_text(chunk)
