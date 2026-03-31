"""Feature 1: Tạo Đơn qua Telegram Bot.

Conversation-based flow for creating leave, overtime, business trip, and check-in applications.
"""

import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from bot.auth.handler import require_auth
from bot.erp_client import ERPClient, AuthenticationError, APIError
from bot.config import (
    SELECT_APP_TYPE,
    SELECT_LEAVE_TYPE,
    ENTER_START_DATE,
    ENTER_END_DATE,
    ENTER_REASON,
    ENTER_OT_DATE,
    ENTER_OT_START,
    ENTER_OT_END,
    ENTER_OT_NOTE,
    SELECT_TRIP_TYPE,
    ENTER_TRIP_LOCATION,
    SELECT_TRIP_REASON,
    SELECT_TRANSPORT,
    ENTER_CHECKIN_TIME,
    ENTER_CHECKIN_REASON,
    SELECT_APPROVER,
    CONFIRM_APPLICATION,
)
from bot.utils.keyboards import (
    application_type_keyboard,
    leave_type_keyboard,
    trip_type_keyboard,
    trip_reason_keyboard,
    transport_method_keyboard,
    confirm_keyboard,
    back_to_menu_keyboard,
    my_app_keyboard,
)
from bot.utils.formatters import format_confirm_application, format_application_summary

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

VIETNAM_UTC_OFFSET = timedelta(hours=7)


def _parse_date(text: str) -> str:
    """Parse DD/MM/YYYY to ISO format. Raises ValueError on bad input."""
    text = text.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%dT00:00:00.000Z")
        except ValueError:
            continue
    raise ValueError(f"Không thể đọc ngày: {text}")


def _parse_date_time_vn(text: str) -> str:
    """Parse 'DD/MM/YYYY HH:MM' as Vietnam local time and return ISO UTC string.

    Example: '01/04/2026 09:00' (9 AM Vietnam) -> '2026-04-01T02:00:00.000Z' (UTC)
    """
    text = text.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            local_dt = datetime.strptime(text, fmt)
            utc_dt = local_dt - VIETNAM_UTC_OFFSET
            return utc_dt.strftime("%Y-%m-%dT%H:%M:00.000Z")
        except ValueError:
            continue
    raise ValueError(f"Không thể đọc thời gian: {text}. Dùng định dạng DD/MM/YYYY HH:MM")


def _parse_datetime(date_str: str, time_str: str) -> str:
    """Combine DD/MM/YYYY and HH:MM into ISO format."""
    text = f"{date_str.strip()} {time_str.strip()}"
    for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:00.000Z")
        except ValueError:
            continue
    raise ValueError(f"Không thể đọc thời gian: {text}")


def _parse_time_on_date(date_iso: str, time_str: str) -> str:
    """Given an ISO date and HH:MM, produce an ISO datetime."""
    try:
        base = datetime.strptime(date_iso[:10], "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Ngày không hợp lệ: {date_iso}")
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Thời gian không hợp lệ: {time_str}. Dùng định dạng HH:MM")
    h, m = int(parts[0]), int(parts[1])
    dt = base.replace(hour=h, minute=m)
    return dt.strftime("%Y-%m-%dT%H:%M:00.000Z")


# ── Entry Point ───────────────────────────────────────────────────────────────

@require_auth
async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry: /taodon or menu_create callback."""
    context.user_data["app_draft"] = {}

    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()

    await msg.reply_text(
        "📝 <b>Tạo đơn mới</b>\n\nChọn loại đơn:",
        parse_mode="HTML",
        reply_markup=application_type_keyboard(),
    )
    return SELECT_APP_TYPE


# ── Step 1: Select Application Type ──────────────────────────────────────────

async def select_app_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle application type selection."""
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. "apptype_LEAVE"

    if data == "cancel":
        await query.edit_message_text("❌ Đã hủy tạo đơn.", reply_markup=back_to_menu_keyboard())
        return ConversationHandler.END

    app_type = data.replace("apptype_", "")
    context.user_data["app_draft"] = {"type": app_type}

    if app_type == "LEAVE":
        # Fetch leave types
        client: ERPClient = context.user_data["erp_client"]
        try:
            leave_types = await client.get_leave_types()
            context.user_data["leave_types_cache"] = leave_types
            await query.edit_message_text(
                "🏖️ <b>Nghỉ phép</b>\n\nChọn loại nghỉ:",
                parse_mode="HTML",
                reply_markup=leave_type_keyboard(leave_types),
            )
            return SELECT_LEAVE_TYPE
        except AuthenticationError as e:
            await query.edit_message_text(str(e))
            return ConversationHandler.END
        except Exception as e:
            logger.error("Failed to fetch leave types: %s", e)
            await query.edit_message_text(f"❌ Lỗi: {e}")
            return ConversationHandler.END

    elif app_type == "OVERTIME":
        await query.edit_message_text(
            "⏰ <b>Tăng ca</b>\n\n"
            "Nhập ngày OT (DD/MM/YYYY):",
            parse_mode="HTML",
        )
        return ENTER_OT_DATE

    elif app_type == "BUSINESS_TRIP":
        await query.edit_message_text(
            "✈️ <b>Công tác</b>\n\nChọn loại công tác:",
            parse_mode="HTML",
            reply_markup=trip_type_keyboard(),
        )
        return SELECT_TRIP_TYPE

    elif app_type == "CHECKIN":
        await query.edit_message_text(
            "📋 <b>Chấm công</b>\n\n"
            "Nhập thời gian chấm công (DD/MM/YYYY HH:MM):",
            parse_mode="HTML",
        )
        return ENTER_CHECKIN_TIME


# ── LEAVE Flow ────────────────────────────────────────────────────────────────

async def select_leave_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_to_type":
        await query.edit_message_text(
            "📝 <b>Tạo đơn mới</b>\n\nChọn loại đơn:",
            parse_mode="HTML",
            reply_markup=application_type_keyboard(),
        )
        return SELECT_APP_TYPE

    leave_type = data.replace("leavetype_", "")
    context.user_data["app_draft"]["leaveType"] = leave_type

    await query.edit_message_text(
        f"🏖️ Loại nghỉ: <b>{leave_type}</b>\n\n"
        "Nhập ngày giờ bắt đầu nghỉ (DD/MM/YYYY HH:MM):\n"
        "Ví dụ: 01/04/2026 09:00",
        parse_mode="HTML",
    )
    return ENTER_START_DATE


async def enter_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        start_iso = _parse_date_time_vn(update.message.text)
    except ValueError as e:
        await update.message.reply_text(
            f"⚠️ {e}\nNhập lại ngày giờ bắt đầu (DD/MM/YYYY HH:MM):\n"
            "Ví dụ: 01/04/2026 09:00"
        )
        return ENTER_START_DATE

    context.user_data["app_draft"]["_start"] = start_iso

    await update.message.reply_text(
        "Nhập ngày giờ kết thúc nghỉ (DD/MM/YYYY HH:MM):\n"
        "Ví dụ: 01/04/2026 18:00"
    )
    return ENTER_END_DATE


async def enter_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        end_iso = _parse_date_time_vn(update.message.text)
    except ValueError as e:
        await update.message.reply_text(
            f"⚠️ {e}\nNhập lại ngày giờ kết thúc (DD/MM/YYYY HH:MM):\n"
            "Ví dụ: 01/04/2026 18:00"
        )
        return ENTER_END_DATE

    start_iso = context.user_data["app_draft"]["_start"]

    # Calculate approximate days
    try:
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        days = max(1, (end_dt.date() - start_dt.date()).days + 1)
    except Exception:
        days = 1

    context.user_data["app_draft"]["leaveDates"] = [{
        "startTime": start_iso,
        "endTime": end_iso,
        "days": days,
    }]

    await update.message.reply_text("📝 Nhập lý do nghỉ phép:")
    return ENTER_REASON


async def enter_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["app_draft"]["reason"] = update.message.text.strip()

    # Show confirmation
    draft = context.user_data["app_draft"]
    # Clean up internal fields
    draft_clean = {k: v for k, v in draft.items() if not k.startswith("_")}
    text = format_confirm_application(draft_clean)

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=confirm_keyboard())
    return CONFIRM_APPLICATION


# ── OVERTIME Flow ─────────────────────────────────────────────────────────────

async def enter_ot_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        ot_date_iso = _parse_date(update.message.text)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}\nNhập lại ngày OT (DD/MM/YYYY):")
        return ENTER_OT_DATE

    context.user_data["app_draft"]["_ot_date"] = ot_date_iso
    context.user_data["app_draft"]["_ot_date_display"] = update.message.text.strip()

    await update.message.reply_text("Nhập giờ bắt đầu OT (HH:MM, ví dụ: 18:00):")
    return ENTER_OT_START


async def enter_ot_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        ot_date = context.user_data["app_draft"]["_ot_date"]
        start_iso = _parse_time_on_date(ot_date, update.message.text)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}\nNhập lại giờ bắt đầu (HH:MM):")
        return ENTER_OT_START

    context.user_data["app_draft"]["_ot_start"] = start_iso

    await update.message.reply_text("Nhập giờ kết thúc OT (HH:MM, ví dụ: 20:00):")
    return ENTER_OT_END


async def enter_ot_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        ot_date = context.user_data["app_draft"]["_ot_date"]
        end_iso = _parse_time_on_date(ot_date, update.message.text)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}\nNhập lại giờ kết thúc (HH:MM):")
        return ENTER_OT_END

    start_iso = context.user_data["app_draft"]["_ot_start"]
    context.user_data["app_draft"]["_ot_end"] = end_iso

    # Calculate hours
    try:
        s = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        hours = round((e - s).total_seconds() / 3600, 1)
    except Exception:
        hours = 0

    context.user_data["app_draft"]["overtimeDetails"] = [{
        "otDate": context.user_data["app_draft"]["_ot_date"][:10],
        "startTime": start_iso,
        "endTime": end_iso,
        "hours": hours,
    }]

    await update.message.reply_text("📝 Nhập ghi chú OT (hoặc gửi 'skip' để bỏ qua):")
    return ENTER_OT_NOTE


async def enter_ot_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "skip":
        context.user_data["app_draft"]["overtimeDetails"][0]["note"] = text
        context.user_data["app_draft"]["reason"] = text
    else:
        context.user_data["app_draft"]["reason"] = "Tăng ca"

    # Show confirmation
    draft = context.user_data["app_draft"]
    draft_clean = {k: v for k, v in draft.items() if not k.startswith("_")}
    confirm_text = format_confirm_application(draft_clean)
    await update.message.reply_text(confirm_text, parse_mode="HTML", reply_markup=confirm_keyboard())
    return CONFIRM_APPLICATION


# ── BUSINESS TRIP Flow ────────────────────────────────────────────────────────

async def select_trip_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_to_type":
        await query.edit_message_text(
            "📝 <b>Tạo đơn mới</b>\n\nChọn loại đơn:",
            parse_mode="HTML",
            reply_markup=application_type_keyboard(),
        )
        return SELECT_APP_TYPE

    trip_type = data.replace("triptype_", "")
    context.user_data["app_draft"]["businessTripDetails"] = {"tripType": trip_type}

    await query.edit_message_text(
        "✈️ Nhập ngày bắt đầu công tác (DD/MM/YYYY):",
        parse_mode="HTML",
    )
    return ENTER_START_DATE  # We reuse start/end date but with trip context


async def enter_trip_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start date for business trip — shares ENTER_START_DATE state with leave."""
    try:
        start_iso = _parse_date(update.message.text)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}\nNhập lại ngày bắt đầu (DD/MM/YYYY):")
        return ENTER_START_DATE

    start_iso = start_iso.replace("T00:00:00", "T08:00:00")
    context.user_data["app_draft"]["businessTripDetails"]["startTime"] = start_iso

    await update.message.reply_text("Nhập ngày kết thúc công tác (DD/MM/YYYY):")
    return ENTER_END_DATE


async def enter_trip_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """End date for business trip — shares ENTER_END_DATE state with leave."""
    try:
        end_iso = _parse_date(update.message.text)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}\nNhập lại ngày kết thúc (DD/MM/YYYY):")
        return ENTER_END_DATE

    end_iso = end_iso.replace("T00:00:00", "T17:00:00")
    context.user_data["app_draft"]["businessTripDetails"]["endTime"] = end_iso

    await update.message.reply_text("📍 Nhập địa điểm công tác:")
    return ENTER_TRIP_LOCATION


async def enter_trip_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["app_draft"]["businessTripDetails"]["location"] = update.message.text.strip()
    await update.message.reply_text(
        "💼 Chọn lý do công tác:",
        reply_markup=trip_reason_keyboard(),
    )
    return SELECT_TRIP_REASON


async def select_trip_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    reason = query.data.replace("tripreason_", "")
    context.user_data["app_draft"]["businessTripDetails"]["reason"] = reason
    context.user_data["app_draft"]["reason"] = f"Công tác - {reason}"

    await query.edit_message_text(
        "🚗 Chọn phương tiện di chuyển:",
        reply_markup=transport_method_keyboard(),
    )
    return SELECT_TRANSPORT


async def select_transport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    transport = query.data.replace("transport_", "")
    context.user_data["app_draft"]["businessTripDetails"]["transportMethod"] = transport

    # Show confirmation
    draft = context.user_data["app_draft"]
    draft_clean = {k: v for k, v in draft.items() if not k.startswith("_")}
    confirm_text = format_confirm_application(draft_clean)
    await query.edit_message_text(confirm_text, parse_mode="HTML", reply_markup=confirm_keyboard())
    return CONFIRM_APPLICATION


# ── CHECKIN Flow ──────────────────────────────────────────────────────────────

async def enter_checkin_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    # Accept "DD/MM/YYYY HH:MM" format
    try:
        parts = text.split()
        if len(parts) == 2:
            date_str, time_str = parts
            date_iso = _parse_date(date_str)
            check_time_iso = _parse_time_on_date(date_iso, time_str)
        else:
            # Try as ISO
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            check_time_iso = dt.strftime("%Y-%m-%dT%H:%M:00.000Z")
    except (ValueError, IndexError) as e:
        await update.message.reply_text(
            f"⚠️ Không thể đọc thời gian: {text}\n"
            "Nhập theo định dạng: DD/MM/YYYY HH:MM"
        )
        return ENTER_CHECKIN_TIME

    context.user_data["app_draft"]["checkinDetails"] = [{"checkTime": check_time_iso}]

    await update.message.reply_text("📝 Nhập lý do chấm công bổ sung:")
    return ENTER_CHECKIN_REASON


async def enter_checkin_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason_text = update.message.text.strip()
    context.user_data["app_draft"]["checkinDetails"][0]["reason"] = reason_text
    context.user_data["app_draft"]["reason"] = reason_text

    draft = context.user_data["app_draft"]
    draft_clean = {k: v for k, v in draft.items() if not k.startswith("_")}
    confirm_text = format_confirm_application(draft_clean)
    await update.message.reply_text(confirm_text, parse_mode="HTML", reply_markup=confirm_keyboard())
    return CONFIRM_APPLICATION


async def _ask_for_approver(message_obj, context: ContextTypes.DEFAULT_TYPE, client: ERPClient) -> int:
    """Fetch potential approvers and show an inline keyboard to pick them (multi-select)."""
    try:
        approvers = await client.get_potential_approvers()
    except Exception as e:
        logger.warning("Could not fetch approvers: %s", e)
        approvers = []

    context.user_data["_approvers_cache"] = approvers
    context.user_data["_selected_approvers"] = []  # list of {approverId, index, name}

    if not approvers:
        await message_obj.reply_text(
            "⚠️ Không tìm thấy người duyệt nào trong hệ thống. Đơn sẽ được gửi không có người duyệt.\n"
            "Gõ /cancel để hủy."
        )
        return CONFIRM_APPLICATION

    return await _show_approver_keyboard(message_obj, context, approvers, edit=False)


async def _show_approver_keyboard(target, context, approvers, edit=True):
    """Show the approver keyboard with current selections marked."""
    selected_ids = {a["approverId"] for a in context.user_data.get("_selected_approvers", [])}
    selected_list = context.user_data.get("_selected_approvers", [])

    buttons = []
    for a in approvers[:15]:
        aid = a.get("id", "")
        name = f"{a.get('firstName', '')} {a.get('lastName', '')}".strip() or a.get('email', 'N/A')
        role = a.get('role', '')
        prefix = "✅ " if aid in selected_ids else ""
        buttons.append([
            InlineKeyboardButton(f"{prefix}{name} ({role})", callback_data=f"approver_{aid}")
        ])

    # Show "Done" button only when at least 1 approver is selected
    bottom_row = []
    if selected_list:
        bottom_row.append(InlineKeyboardButton(f"✔️ Xong ({len(selected_list)} người)", callback_data="approver_done"))
    bottom_row.append(InlineKeyboardButton("❌ Hủy", callback_data="cancel"))
    buttons.append(bottom_row)

    text = (
        f"👥 <b>Chọn người duyệt đơn</b> (đã chọn: {len(selected_list)})\n"
        "Bấm vào tên để chọn/bỏ chọn, bấm \"Xong\" khi hoàn tất."
    )

    if edit:
        await target.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    return SELECT_APPROVER


async def select_approver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle approver toggle/done and submit the application."""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.pop("app_draft", None)
        context.user_data.pop("_approvers_cache", None)
        context.user_data.pop("_selected_approvers", None)
        await query.edit_message_text("❌ Đã hủy tạo đơn.", reply_markup=back_to_menu_keyboard())
        return ConversationHandler.END

    approvers_cache = context.user_data.get("_approvers_cache", [])
    selected = context.user_data.setdefault("_selected_approvers", [])

    if query.data != "approver_done":
        # Toggle approver selection
        approver_id = query.data.replace("approver_", "")
        existing_idx = next((i for i, a in enumerate(selected) if a["approverId"] == approver_id), None)
        if existing_idx is not None:
            selected.pop(existing_idx)
            # Re-index
            for i, a in enumerate(selected):
                a["index"] = i
        else:
            approver = next((a for a in approvers_cache if a.get("id") == approver_id), None)
            name = ""
            if approver:
                name = f"{approver.get('firstName', '')} {approver.get('lastName', '')}".strip()
            selected.append({"approverId": approver_id, "index": len(selected), "name": name})

        # Re-show keyboard with updated selections
        return await _show_approver_keyboard(query.message, context, approvers_cache, edit=True)

    # "Done" pressed — submit the application
    if not selected:
        await query.answer("Vui lòng chọn ít nhất 1 người duyệt!", show_alert=True)
        return SELECT_APPROVER

    # Build payload
    draft = context.user_data.get("app_draft", {})
    payload = {k: v for k, v in draft.items() if not k.startswith("_")}
    payload["approvers"] = [{"approverId": a["approverId"], "index": a["index"]} for a in selected]
    payload.setdefault("attachmentFileIds", [])

    approver_names = ", ".join(a.get("name", "?") for a in selected)

    logger.info("Submitting time application payload: %s", payload)

    client: ERPClient = context.user_data.get("erp_client")
    if not client:
        client = ERPClient(update.effective_chat.id)

    try:
        result = await client.create_time_application(payload)
        app_id = result.get("id", "N/A")
        status = result.get("status", "PENDING")

        await query.edit_message_text(
            f"✅ <b>Đơn đã được tạo thành công!</b>\n\n"
            f"🆔 Mã đơn: <code>{app_id}</code>\n"
            f"📊 Trạng thái: {status}\n"
            f"👤 Người duyệt: {approver_names}",
            parse_mode="HTML",
            reply_markup=back_to_menu_keyboard(),
        )
    except AuthenticationError as e:
        await query.edit_message_text(str(e))
    except APIError as e:
        logger.error("API error creating application: %s", e)
        await query.edit_message_text(f"❌ {e}", reply_markup=back_to_menu_keyboard())
    except Exception as e:
        logger.error("Create application error: %s", e)
        await query.edit_message_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())

    context.user_data.pop("app_draft", None)
    context.user_data.pop("_approvers_cache", None)
    context.user_data.pop("_selected_approvers", None)
    return ConversationHandler.END


async def confirm_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirm_yes — move to approver selection step."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        context.user_data.pop("app_draft", None)
        await query.edit_message_text("❌ Đã hủy tạo đơn.", reply_markup=back_to_menu_keyboard())
        return ConversationHandler.END

    client: ERPClient = context.user_data.get("erp_client")
    if not client:
        client = ERPClient(update.effective_chat.id)

    return await _ask_for_approver(query.message, context, client)


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current conversation at any point."""
    context.user_data.pop("app_draft", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Đã hủy.", reply_markup=back_to_menu_keyboard())
    elif update.message:
        await update.message.reply_text("❌ Đã hủy.", reply_markup=back_to_menu_keyboard())
    return ConversationHandler.END


# ── My Applications (list view) ──────────────────────────────────────────────

@require_auth
async def my_applications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /donganday — show user's recent applications, each with a cancel button."""
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()

    client: ERPClient = context.user_data["erp_client"]
    try:
        data = await client.get_my_applications(page=1, limit=10, sortOrder="desc")
        items = data.get("data", data.get("items", []))

        if not items:
            await msg.reply_text(
                "📭 Bạn chưa có đơn nào.\nDùng /taodon để tạo đơn mới.",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        await msg.reply_text(
            f"📋 <b>Đơn gần đây của bạn ({len(items)}):</b>",
            parse_mode="HTML",
        )

        for app in items:
            app_id = app.get("id", "")
            status = app.get("status", "")
            card_text = format_application_summary(app)
            kb = my_app_keyboard(app_id, status)
            await msg.reply_text(
                card_text,
                parse_mode="HTML",
                reply_markup=kb if kb.inline_keyboard else back_to_menu_keyboard(),
            )

    except AuthenticationError as e:
        await msg.reply_text(str(e))
    except Exception as e:
        logger.error("Error fetching applications: %s", e)
        await msg.reply_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())


@require_auth
async def handle_cancel_app(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle cancelapp_{id} callback — cancel the application."""
    query = update.callback_query
    await query.answer()

    app_id = query.data.replace("cancelapp_", "")
    client: ERPClient = context.user_data["erp_client"]

    try:
        await client.cancel_application(app_id)
        await query.edit_message_text(
            f"⚫ <b>Đơn đã được hủy.</b>\n"
            f"🆔 <code>{app_id}</code>",
            parse_mode="HTML",
            reply_markup=back_to_menu_keyboard(),
        )
    except AuthenticationError as e:
        await query.edit_message_text(str(e))
    except APIError as e:
        await query.edit_message_text(f"❌ {e}", reply_markup=back_to_menu_keyboard())
    except Exception as e:
        logger.error("Cancel application error: %s", e)
        await query.edit_message_text(f"❌ Lỗi: {e}", reply_markup=back_to_menu_keyboard())


# ── Build Conversation Handler ────────────────────────────────────────────────

def build_create_application_handler() -> ConversationHandler:
    """Build and return the ConversationHandler for creating applications.

    Because LEAVE and BUSINESS_TRIP share ENTER_START_DATE / ENTER_END_DATE states,
    the handlers check the draft type to route correctly.
    """

    async def enter_start_date_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        draft = context.user_data.get("app_draft", {})
        if draft.get("type") == "BUSINESS_TRIP":
            return await enter_trip_start_date(update, context)
        return await enter_start_date(update, context)

    async def enter_end_date_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        draft = context.user_data.get("app_draft", {})
        if draft.get("type") == "BUSINESS_TRIP":
            return await enter_trip_end_date(update, context)
        return await enter_end_date(update, context)

    return ConversationHandler(
        entry_points=[
            CommandHandler("taodon", start_create),
            CallbackQueryHandler(start_create, pattern="^menu_create$"),
        ],
        states={
            SELECT_APP_TYPE: [
                CallbackQueryHandler(select_app_type, pattern="^apptype_"),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
            ],
            SELECT_LEAVE_TYPE: [
                CallbackQueryHandler(select_leave_type, pattern="^leavetype_"),
                CallbackQueryHandler(select_leave_type, pattern="^back_to_type$"),
            ],
            ENTER_START_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_start_date_router),
            ],
            ENTER_END_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_end_date_router),
            ],
            ENTER_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_reason),
            ],
            ENTER_OT_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_ot_date),
            ],
            ENTER_OT_START: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_ot_start),
            ],
            ENTER_OT_END: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_ot_end),
            ],
            ENTER_OT_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_ot_note),
            ],
            SELECT_TRIP_TYPE: [
                CallbackQueryHandler(select_trip_type, pattern="^triptype_"),
                CallbackQueryHandler(select_trip_type, pattern="^back_to_type$"),
            ],
            ENTER_TRIP_LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_trip_location),
            ],
            SELECT_TRIP_REASON: [
                CallbackQueryHandler(select_trip_reason, pattern="^tripreason_"),
            ],
            SELECT_TRANSPORT: [
                CallbackQueryHandler(select_transport, pattern="^transport_"),
            ],
            ENTER_CHECKIN_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_checkin_time),
            ],
            ENTER_CHECKIN_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_checkin_reason),
            ],
            CONFIRM_APPLICATION: [
                CallbackQueryHandler(confirm_application, pattern="^confirm_"),
            ],
            SELECT_APPROVER: [
                CallbackQueryHandler(select_approver, pattern="^approver_"),
                CallbackQueryHandler(select_approver, pattern="^approver_done$"),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
        ],
        allow_reentry=True,
    )
