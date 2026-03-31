"""B.E.A.R BOT — Main entry point.

Back-office Efficiency Agent & Ranking Bot for Twendee ERP.
"""

import asyncio
import logging
import signal

from telegram import Update, BotCommand
from telegram.error import TimedOut, NetworkError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from bot.config import TELEGRAM_BOT_TOKEN
from bot import database
from bot.auth.handler import build_login_handler, logout_command, status_command, require_auth
from bot.features.create_application import build_create_application_handler, my_applications, handle_cancel_app
from bot.features.approve_application import (
    list_pending_approvals,
    handle_approve,
    handle_reject_start,
    handle_reject_reason,
    handle_detail,
    setup_approval_polling,
)
from bot.features.account_management import (
    offboard_command,
    offboard_confirm,
    offboard_cancel,
    setup_offboarding_polling,
)
from bot.features.ai_report import build_report_handler
from bot.utils.keyboards import main_menu_keyboard, back_to_menu_keyboard

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Reduce noise from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)


# ── Global Handlers ──────────────────────────────────────────────────────────

async def start_command(update: Update, context) -> None:
    """Handle /start — welcome message with main menu."""
    user = update.effective_user
    session = await database.get_session(update.effective_chat.id)

    if session:
        name = session.get("full_name", user.first_name)
        await update.message.reply_text(
            f"🐻 <b>Chào {name}!</b>\n\n"
            f"Chào mừng bạn đến với <b>B.E.A.R BOT</b>\n"
            f"<i>Back-office Efficiency Agent & Ranking</i>\n\n"
            f"Chọn chức năng bạn muốn sử dụng:",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"🐻 <b>Chào mừng đến với B.E.A.R BOT!</b>\n\n"
            f"<i>Back-office Efficiency Agent & Ranking</i>\n\n"
            f"Bot giúp bạn quản lý đơn từ, duyệt đơn và quản lý tài khoản ERP "
            f"ngay trên Telegram.\n\n"
            f"🔐 Để bắt đầu, hãy đăng nhập:\n"
            f"/login — Đăng nhập bằng Google",
            parse_mode="HTML",
        )


async def help_command(update: Update, context) -> None:
    """Handle /help — list all commands."""
    await update.message.reply_text(
        "🐻 <b>B.E.A.R BOT — Danh sách lệnh</b>\n\n"
        "🔐 <b>Tài khoản:</b>\n"
        "/login — Đăng nhập bằng Google\n"
        "/token — Lưu token sau khi đăng nhập\n"
        "/logout — Đăng xuất\n"
        "/status — Xem trạng thái đăng nhập\n\n"
        "📝 <b>Quản lý đơn:</b>\n"
        "/taodon — Tạo đơn mới (nghỉ phép, OT, công tác, chấm công)\n"
        "/donganday — Xem đơn gần đây của tôi\n\n"
        "✅ <b>Duyệt đơn:</b>\n"
        "/duyetdon — Xem đơn chờ duyệt\n\n"
        "👤 <b>Quản lý tài khoản (Admin/HR):</b>\n"
        "/offboard — Vô hiệu hóa tài khoản nhân viên\n\n"
        "🤖 <b>Báo cáo AI:</b>\n"
        "/report — Tạo báo cáo bằng AI\n\n"
        "❌ /cancel — Hủy thao tác hiện tại",
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )


async def menu_callback(update: Update, context) -> None:
    """Handle main menu callbacks."""
    query = update.callback_query
    data = query.data

    if data == "menu_main":
        await query.answer()
        session = await database.get_session(update.effective_chat.id)
        if session:
            name = session.get("full_name", "")
            await query.edit_message_text(
                f"🐻 <b>Menu chính</b>\n\nXin chào, {name}!\nChọn chức năng:",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await query.edit_message_text(
                "⚠️ Bạn chưa đăng nhập. Dùng /login để đăng nhập.",
            )

    elif data == "menu_my_apps":
        await my_applications(update, context)

    elif data == "menu_approve":
        await list_pending_approvals(update, context)

    elif data == "menu_profile":
        await query.answer()
        session = await database.get_session(update.effective_chat.id)
        if session:
            await query.edit_message_text(
                f"👤 <b>Thông tin tài khoản</b>\n\n"
                f"👤 Tên: {session.get('full_name', 'N/A')}\n"
                f"📧 Email: {session.get('email', 'N/A')}\n"
                f"🔑 Vai trò: {session.get('roles', 'N/A')}",
                parse_mode="HTML",
                reply_markup=back_to_menu_keyboard(),
            )
        else:
            await query.edit_message_text("⚠️ Bạn chưa đăng nhập. Dùng /login")

    elif data == "noop":
        await query.answer()


async def reject_reason_handler(update: Update, context) -> None:
    """Global text handler that intercepts rejection reasons."""
    if "pending_reject_id" in context.user_data:
        await handle_reject_reason(update, context)


async def error_handler(update: object, context) -> None:
    """Global error handler — silence transient network errors, log the rest."""
    err = context.error
    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning("Telegram network error (will retry): %s", err)
        return
    logger.error("Unhandled exception: %s", err, exc_info=err)


# ── Post-init: Set Bot Commands ──────────────────────────────────────────────

async def post_init(application: Application) -> None:
    """Set bot commands in Telegram menu."""
    commands = [
        BotCommand("start", "Trang chủ"),
        BotCommand("login", "Đăng nhập bằng Google"),
        BotCommand("token", "Lưu token đăng nhập"),
        BotCommand("status", "Xem trạng thái đăng nhập"),
        BotCommand("logout", "Đăng xuất"),
        BotCommand("taodon", "Tạo đơn mới"),
        BotCommand("donganday", "Xem đơn gần đây"),
        BotCommand("duyetdon", "Duyệt đơn chờ"),
        BotCommand("offboard", "Offboard nhân viên (Admin/HR)"),
        BotCommand("report", "Tạo báo cáo bằng AI"),
        BotCommand("help", "Xem danh sách lệnh"),
        BotCommand("cancel", "Hủy thao tác hiện tại"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set successfully")


# ── Application Builder ──────────────────────────────────────────────────────

def build_application() -> Application:
    """Build the bot application with all handlers registered."""

    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set! Check your .env file.")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(30)
        .build()
    )
    app.add_error_handler(error_handler)

    # ── Conversation handlers (must be added first for priority) ──────────
    create_app_handler = build_create_application_handler()
    app.add_handler(create_app_handler)

    # ── AI Report conversation ─────────────────────────────────────────────
    app.add_handler(build_report_handler())

    # ── Login conversation (must be before generic command handlers) ────────
    app.add_handler(build_login_handler())

    # ── Command handlers ──────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("logout", logout_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("donganday", my_applications))
    app.add_handler(CommandHandler("duyetdon", list_pending_approvals))
    app.add_handler(CommandHandler("offboard", offboard_command))

    # ── Callback query handlers ───────────────────────────────────────────
    # Menu
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^noop$"))

    # Approval actions
    app.add_handler(CallbackQueryHandler(handle_approve, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(handle_reject_start, pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(handle_detail, pattern="^detail_"))

    # Offboard actions
    app.add_handler(CallbackQueryHandler(offboard_confirm, pattern="^offboard_confirm_"))
    app.add_handler(CallbackQueryHandler(offboard_cancel, pattern="^offboard_cancel$"))

    # Cancel application (from my-apps list)
    app.add_handler(CallbackQueryHandler(handle_cancel_app, pattern="^cancelapp_"))

    # ── Text handler for rejection reasons (low priority) ─────────────────
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        reject_reason_handler,
    ), group=1)

    # ── Periodic jobs ─────────────────────────────────────────────────────
    setup_approval_polling(app, interval=60)
    setup_offboarding_polling(app, interval=120)

    return app


# ── Entry Point ───────────────────────────────────────────────────────────────

async def _async_main() -> None:
    """Async entry point — runs DB init and bot inside a single event loop."""
    await database.init_db()

    app = build_application()

    logger.info("🐻 B.E.A.R BOT starting...")
    logger.info("Bot is using polling mode")

    # Use a stop event triggered by SIGINT/SIGTERM for clean shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )
    logger.info("Bot is running. Press Ctrl+C to stop.")

    # Wait until Ctrl+C
    await stop_event.wait()

    logger.info("Shutting down...")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()


def main() -> None:
    """Start the bot."""
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")


if __name__ == "__main__":
    main()
