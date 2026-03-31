"""Feature 3: Bot Tự Động Cắt Email & Tài Khoản ERP.

Admin/HR can offboard employees via /offboard command.
Also includes automated detection of approved OFFBOARDING applications.
"""

import logging
from typing import Dict, Set

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application

from bot.auth.handler import require_auth
from bot.erp_client import ERPClient, AuthenticationError, APIError
from bot import database
from bot.utils.keyboards import back_to_menu_keyboard
from bot.utils.formatters import format_employee_info

logger = logging.getLogger(__name__)

# Track offboarding applications already processed
_processed_offboards: Set[str] = set()


def _is_admin_or_hr(session: dict) -> bool:
    """Check if the user has admin or HR role."""
    roles = session.get("roles", "")
    user_roles = set(r.strip().upper() for r in roles.split(",")) if roles else set()
    return bool(user_roles & {"ADMIN", "HR", "BOD", "MANAGEMENT"})


@require_auth
async def offboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /offboard <search_term> — search and deactivate an employee.

    Flow:
    1. Search employee by code/name/email
    2. Show employee info with confirm button
    3. On confirm, update status to INACTIVE
    """
    session = context.user_data.get("session", {})
    if not _is_admin_or_hr(session):
        await update.message.reply_text(
            "⛔ Bạn không có quyền thực hiện chức năng này.\n"
            "Chỉ Admin/HR mới có thể offboard nhân viên.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Vui lòng cung cấp mã nhân viên hoặc tên:\n"
            "<code>/offboard EMP001</code>\n"
            "<code>/offboard Nguyễn Văn A</code>",
            parse_mode="HTML",
        )
        return

    search_term = " ".join(context.args)
    client: ERPClient = context.user_data["erp_client"]

    try:
        data = await client.get_employees(search=search_term, page=1, limit=5)
        items = data.get("data", data.get("items", []))

        if not items:
            await update.message.reply_text(
                f"❌ Không tìm thấy nhân viên: <b>{search_term}</b>",
                parse_mode="HTML",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        if len(items) == 1:
            # Single result — show detail with confirm
            emp = items[0]
            profile = emp.get("employeeProfile", emp)
            profile_id = profile.get("id", emp.get("id", ""))
            emp_info = format_employee_info(profile)

            name = profile.get("fullName") or f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip() or "N/A"
            context.user_data["offboard_target"] = {
                "profile_id": profile_id,
                "name": name,
                "code": profile.get("employeeCode", "N/A"),
            }

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚠️ Xác nhận OFF", callback_data=f"offboard_confirm_{profile_id}"),
                    InlineKeyboardButton("❌ Hủy", callback_data="offboard_cancel"),
                ]
            ])

            await update.message.reply_text(
                f"⚠️ <b>Offboard tài khoản</b>\n\n"
                f"{emp_info}\n\n"
                f"Bạn có chắc muốn vô hiệu hóa tài khoản này?",
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            # Multiple results — show list
            lines = [f"🔍 Tìm thấy {len(items)} tài khoản:\n"]
            for i, emp in enumerate(items, 1):
                profile = emp.get("employeeProfile", emp)
                name = profile.get("fullName") or f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip() or "N/A"
                code = profile.get("employeeCode", "N/A")
                dept = profile.get("department", "")
                status = profile.get("status", "")
                lines.append(f"{i}. <b>{name}</b> ({code}) — {dept} [{status}]")

            lines.append(f"\nDùng /offboard với mã nhân viên cụ thể hơn.")

            await update.message.reply_text(
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=back_to_menu_keyboard(),
            )

    except AuthenticationError as e:
        await update.message.reply_text(str(e))
    except Exception as e:
        logger.error("Offboard search error: %s", e)
        await update.message.reply_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())


@require_auth
async def offboard_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle offboard_confirm_{id} callback — deactivate the employee."""
    query = update.callback_query
    await query.answer()

    session = context.user_data.get("session", {})
    if not _is_admin_or_hr(session):
        await query.edit_message_text("⛔ Không có quyền.")
        return

    profile_id = query.data.replace("offboard_confirm_", "")
    target = context.user_data.get("offboard_target", {})
    client: ERPClient = context.user_data["erp_client"]

    try:
        result = await client.update_employee_status(profile_id, "INACTIVE")

        await query.edit_message_text(
            f"✅ <b>Đã vô hiệu hóa tài khoản!</b>\n\n"
            f"👤 {target.get('name', 'N/A')}\n"
            f"🔢 Mã NV: {target.get('code', 'N/A')}\n"
            f"📊 Trạng thái: INACTIVE\n\n"
            f"📧 Tài khoản ERP đã bị khóa.",
            parse_mode="HTML",
            reply_markup=back_to_menu_keyboard(),
        )

    except AuthenticationError as e:
        await query.edit_message_text(str(e))
    except APIError as e:
        await query.edit_message_text(f"❌ {e}", reply_markup=back_to_menu_keyboard())
    except Exception as e:
        logger.error("Offboard error: %s", e)
        await query.edit_message_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())

    context.user_data.pop("offboard_target", None)


async def offboard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle offboard_cancel callback."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("offboard_target", None)
    await query.edit_message_text("❌ Đã hủy offboard.", reply_markup=back_to_menu_keyboard())


# ── Auto-detect approved OFFBOARDING applications ────────────────────────────

async def check_approved_offboarding(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job: detect newly approved OFFBOARDING applications and notify HR.

    Runs every 120 seconds. For each admin/HR session, checks for
    approved offboarding applications and sends a notification.
    """
    sessions = await database.get_all_sessions()

    for session in sessions:
        chat_id = session["telegram_chat_id"]
        roles = session.get("roles", "")
        user_roles = set(r.strip().upper() for r in roles.split(",")) if roles else set()

        # Only HR/Admin get notified about offboarding
        if not (user_roles & {"ADMIN", "HR"}):
            continue

        try:
            client = ERPClient(chat_id)
            data = await client.get_my_applications(
                type="OFFBOARDING",
                status="APPROVED",
                page=1,
                limit=5,
            )
            items = data.get("data", data.get("items", []))

            for app in items:
                app_id = app.get("id", "")
                if app_id in _processed_offboards:
                    continue
                _processed_offboards.add(app_id)

                employee = app.get("employee", {}) or {}
                emp_name = employee.get("fullName", "N/A")
                emp_code = employee.get("employeeCode", "")

                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"⚠️ <b>Đơn Offboarding đã được duyệt!</b>\n\n"
                             f"👤 {emp_name} ({emp_code})\n"
                             f"🆔 <code>{app_id}</code>\n\n"
                             f"Dùng /offboard {emp_code} để vô hiệu hóa tài khoản.",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning("Failed to notify offboarding chat %s: %s", chat_id, e)

        except AuthenticationError:
            continue
        except Exception as e:
            logger.error("Offboarding check error for chat %s: %s", chat_id, e)


def setup_offboarding_polling(application: Application, interval: int = 120) -> None:
    """Register the periodic offboarding check job."""
    application.job_queue.run_repeating(
        check_approved_offboarding,
        interval=interval,
        first=30,
        name="offboarding_polling",
    )
