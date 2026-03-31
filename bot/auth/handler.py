"""Authentication handlers — username/password login conversation, /logout, /status."""

import functools
import logging
from typing import Callable

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot import database
from bot.erp_client import ERPClient, AuthenticationError
from bot.config import LOGIN_ENTER_USERNAME, LOGIN_ENTER_PASSWORD
from bot.utils.keyboards import main_menu_keyboard, back_to_menu_keyboard

logger = logging.getLogger(__name__)


# ── Auth guard decorator ──────────────────────────────────────────────────────

def require_auth(func: Callable):
    """Decorator that checks the user has a valid session before running the handler."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.effective_chat.id
        session = await database.get_session(chat_id)
        if session is None:
            await update.effective_message.reply_text(
                "⚠️ Bạn chưa đăng nhập.\n"
                "Dùng /login để đăng nhập.",
                reply_markup=back_to_menu_keyboard(),
            )
            return
        context.user_data["erp_client"] = ERPClient(chat_id)
        context.user_data["session"] = session
        return await func(update, context, *args, **kwargs)

    return wrapper


# ── Login Conversation ────────────────────────────────────────────────────────

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /login — start username/password conversation."""
    chat_id = update.effective_chat.id

    # Already logged in?
    session = await database.get_session(chat_id)
    if session:
        await update.message.reply_text(
            f"✅ Bạn đã đăng nhập với email: <b>{session.get('email', 'N/A')}</b>\n"
            f"Dùng /logout để đăng xuất.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🔐 <b>Đăng nhập ERP</b>\n\n"
        "Nhập <b>email hoặc username</b> của bạn:\n\n"
        "Gửi /cancel để hủy.",
        parse_mode="HTML",
    )
    return LOGIN_ENTER_USERNAME


async def login_enter_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store username, ask for password."""
    context.user_data["login_username"] = update.message.text.strip()

    await update.message.reply_text(
        "🔑 Nhập <b>mật khẩu</b> của bạn:\n\n"
        "<i>Tin nhắn sẽ được xóa ngay sau khi nhận.</i>",
        parse_mode="HTML",
    )
    return LOGIN_ENTER_PASSWORD


async def login_enter_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive password, delete it immediately, call login API, save session."""
    chat_id = update.effective_chat.id
    password = update.message.text.strip()

    # Delete the password message immediately from chat
    try:
        await update.message.delete()
    except Exception:
        pass

    username = context.user_data.pop("login_username", "")
    context.user_data.pop("login_username", None)

    processing_msg = await update.effective_chat.send_message("⏳ Đang đăng nhập...")

    try:
        client = ERPClient(chat_id)
        result = await client.login_with_credentials(username, password)

        # Extract tokens
        access_token = result.get("access_token", result.get("accessToken", ""))
        refresh_token = result.get("refresh_token", result.get("refreshToken", ""))

        if not access_token:
            raise AuthenticationError("Không nhận được token từ server.")

        # Extract user info from response
        user = result.get("user", {}) or {}
        email = user.get("email", username)
        first_name = user.get("firstName", "")
        last_name = user.get("lastName", "")
        full_name = f"{first_name} {last_name}".strip() or username
        erp_user_id = user.get("id", "")
        roles_data = user.get("roles", user.get("role", ""))
        roles = ",".join(roles_data) if isinstance(roles_data, list) else str(roles_data)

        # Save session to DB
        await database.save_session(
            telegram_chat_id=chat_id,
            access_token=access_token,
            refresh_token=refresh_token,
            erp_user_id=erp_user_id,
            email=email,
            full_name=full_name,
            roles=roles,
        )

        await processing_msg.edit_text(
            f"✅ <b>Đăng nhập thành công!</b>\n\n"
            f"👤 Tên: {full_name}\n"
            f"📧 Email: {email}\n"
            f"🔑 Vai trò: {roles or 'N/A'}",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

    except AuthenticationError as e:
        await processing_msg.edit_text(
            f"❌ <b>Đăng nhập thất bại</b>\n\n{e}\n\n"
            "Dùng /login để thử lại.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Login error: %s", e)
        await processing_msg.edit_text(
            f"❌ Lỗi không xác định: {e}\n\nDùng /login để thử lại.",
        )

    return ConversationHandler.END


async def login_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the login conversation."""
    context.user_data.pop("login_username", None)
    await update.message.reply_text("❌ Đã hủy đăng nhập.")
    return ConversationHandler.END


def build_login_handler() -> ConversationHandler:
    """Build the login ConversationHandler."""
    return ConversationHandler(
        entry_points=[CommandHandler("login", login_command)],
        states={
            LOGIN_ENTER_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_enter_username),
            ],
            LOGIN_ENTER_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_enter_password),
            ],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
        allow_reentry=True,
    )


# ── Other auth commands ───────────────────────────────────────────────────────

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /logout — clear the session."""
    chat_id = update.effective_chat.id
    session = await database.get_session(chat_id)
    if session is None:
        await update.message.reply_text("ℹ️ Bạn chưa đăng nhập.")
        return

    await database.delete_session(chat_id)
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Đã đăng xuất thành công.\n"
        "Dùng /login để đăng nhập lại.",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status — show current login status."""
    chat_id = update.effective_chat.id
    session = await database.get_session(chat_id)

    if session is None:
        await update.message.reply_text(
            "❌ Chưa đăng nhập.\nDùng /login để đăng nhập.",
        )
        return

    await update.message.reply_text(
        f"✅ <b>Đã đăng nhập</b>\n\n"
        f"👤 Tên: {session.get('full_name', 'N/A')}\n"
        f"📧 Email: {session.get('email', 'N/A')}\n"
        f"🔑 Vai trò: {session.get('roles', 'N/A')}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
