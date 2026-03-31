"""Feature 2: Duyệt Đơn qua Telegram.

List pending approvals, approve/reject with inline buttons.
Includes a polling job to notify approvers of new pending requests.
"""

import logging
from typing import Dict, Set

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application

from bot.auth.handler import require_auth
from bot.erp_client import ERPClient, AuthenticationError, APIError
from bot import database
from bot.utils.keyboards import approval_action_keyboard, back_to_menu_keyboard
from bot.utils.formatters import (
    format_application_card_for_approval,
    format_application_detail,
)

logger = logging.getLogger(__name__)

# Track which application IDs we've already notified about (per session)
_notified_app_ids: Dict[int, Set[str]] = {}


@require_auth
async def list_pending_approvals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /duyetdon or menu_approve callback — show pending applications for approval."""
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()

    client: ERPClient = context.user_data["erp_client"]

    try:
        data = await client.get_pending_approvals(page=1, limit=20)
        items = data.get("data", data.get("items", []))

        if not items:
            await msg.reply_text(
                "✅ Không có đơn nào đang chờ duyệt!",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        total = data.get("total", data.get("meta", {}).get("total", len(items)))
        await msg.reply_text(
            f"📋 <b>Đơn chờ duyệt ({total}):</b>",
            parse_mode="HTML",
        )

        for app in items:
            app_id = app.get("id", "")
            card_text = format_application_card_for_approval(app)
            await msg.reply_text(
                card_text,
                parse_mode="HTML",
                reply_markup=approval_action_keyboard(app_id),
            )

    except AuthenticationError as e:
        await msg.reply_text(str(e))
    except Exception as e:
        logger.error("Error fetching pending approvals: %s", e)
        await msg.reply_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())


@require_auth
async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle approve_{id} callback — approve the application."""
    query = update.callback_query
    await query.answer()

    app_id = query.data.replace("approve_", "")
    client: ERPClient = context.user_data["erp_client"]

    try:
        result = await client.approve_application(app_id, comments="Approved via Telegram Bot")

        status = result.get("status", "APPROVED")
        employee = result.get("employee", {}) or {}
        emp_name = employee.get("fullName", "")
        if not emp_name:
            user = result.get("user", {}) or {}
            emp_name = f'{user.get("firstName", "")} {user.get("lastName", "")}'.strip()

        await query.edit_message_text(
            f"✅ <b>Đã duyệt đơn!</b>\n\n"
            f"👤 {emp_name}\n"
            f"📊 Trạng thái: {status}\n"
            f"🆔 <code>{app_id}</code>",
            parse_mode="HTML",
            reply_markup=back_to_menu_keyboard(),
        )

    except AuthenticationError as e:
        await query.edit_message_text(str(e))
    except APIError as e:
        await query.edit_message_text(f"❌ {e}", reply_markup=back_to_menu_keyboard())
    except Exception as e:
        logger.error("Approve error: %s", e)
        await query.edit_message_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())


@require_auth
async def handle_reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle reject_{id} callback — ask for rejection reason."""
    query = update.callback_query
    await query.answer()

    app_id = query.data.replace("reject_", "")
    context.user_data["pending_reject_id"] = app_id

    await query.edit_message_text(
        "❌ <b>Từ chối đơn</b>\n\n"
        f"🆔 <code>{app_id}</code>\n\n"
        "Nhập lý do từ chối (hoặc /cancel để hủy):",
        parse_mode="HTML",
    )


async def handle_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the rejection reason text message."""
    app_id = context.user_data.pop("pending_reject_id", None)
    if not app_id:
        return  # Not in reject flow

    chat_id = update.effective_chat.id
    client = ERPClient(chat_id)
    reason = update.message.text.strip()

    try:
        result = await client.reject_application(app_id, comments=reason)

        status = result.get("status", "REJECTED")
        await update.message.reply_text(
            f"❌ <b>Đã từ chối đơn!</b>\n\n"
            f"🆔 <code>{app_id}</code>\n"
            f"📝 Lý do: {reason}\n"
            f"📊 Trạng thái: {status}",
            parse_mode="HTML",
            reply_markup=back_to_menu_keyboard(),
        )

    except AuthenticationError as e:
        await update.message.reply_text(str(e))
    except APIError as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=back_to_menu_keyboard())
    except Exception as e:
        logger.error("Reject error: %s", e)
        await update.message.reply_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())


@require_auth
async def handle_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle detail_{id} callback — show full application details."""
    query = update.callback_query
    await query.answer()

    app_id = query.data.replace("detail_", "")
    client: ERPClient = context.user_data["erp_client"]

    try:
        app = await client.get_application_detail(app_id)
        detail_text = format_application_detail(app)

        # Re-show approval buttons
        await query.edit_message_text(
            detail_text,
            parse_mode="HTML",
            reply_markup=approval_action_keyboard(app_id),
        )

    except AuthenticationError as e:
        await query.edit_message_text(str(e))
    except Exception as e:
        logger.error("Detail error: %s", e)
        await query.edit_message_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())


# ── Notification Polling ──────────────────────────────────────────────────────

async def check_new_approvals(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job: check for new pending approvals and notify users.

    Runs every 60 seconds. For each logged-in user with approver role,
    fetches pending approvals and sends a notification for new ones.
    """
    sessions = await database.get_all_sessions()

    for session in sessions:
        chat_id = session["telegram_chat_id"]
        roles = session.get("roles", "")

        # Only check for users who can approve (HR, MANAGER, ADMIN, BOD, MANAGEMENT)
        approver_roles = {"ADMIN", "HR", "MANAGER", "BOD", "MANAGEMENT"}
        user_roles = set(r.strip().upper() for r in roles.split(",")) if roles else set()
        if not user_roles & approver_roles:
            continue

        try:
            client = ERPClient(chat_id)
            data = await client.get_pending_approvals(page=1, limit=5)
            items = data.get("data", data.get("items", []))

            if not items:
                continue

            # Check for new applications
            if chat_id not in _notified_app_ids:
                _notified_app_ids[chat_id] = set()

            new_apps = []
            for app in items:
                app_id = app.get("id", "")
                if app_id and app_id not in _notified_app_ids[chat_id]:
                    new_apps.append(app)
                    _notified_app_ids[chat_id].add(app_id)

            if new_apps:
                # Send notification
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🔔 <b>Bạn có {len(new_apps)} đơn mới cần duyệt!</b>\n"
                             f"Dùng /duyetdon để xem danh sách.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning("Failed to notify chat %s: %s", chat_id, e)

        except AuthenticationError:
            # Token expired, skip this user
            continue
        except Exception as e:
            logger.error("Polling error for chat %s: %s", chat_id, e)
            continue


def setup_approval_polling(application: Application, interval: int = 60) -> None:
    """Register the periodic approval check job."""
    application.job_queue.run_repeating(
        check_new_approvals,
        interval=interval,
        first=10,  # Start after 10 seconds
        name="approval_polling",
    )
