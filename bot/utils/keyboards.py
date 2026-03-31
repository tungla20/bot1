"""Inline keyboard builders for all bot interactions."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import APPLICATION_TYPES, TRIP_TYPES, TRIP_REASONS, TRANSPORT_METHODS


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu with all features."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Tạo Đơn", callback_data="menu_create")],
        [InlineKeyboardButton("📋 Đơn Của Tôi", callback_data="menu_my_apps")],
        [InlineKeyboardButton("✅ Duyệt Đơn", callback_data="menu_approve")],
        [InlineKeyboardButton("👤 Thông Tin", callback_data="menu_profile")],
    ])


def application_type_keyboard() -> InlineKeyboardMarkup:
    """Application type selection."""
    buttons = []
    for type_code, label in APPLICATION_TYPES.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"apptype_{type_code}")])
    buttons.append([InlineKeyboardButton("❌ Hủy", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def leave_type_keyboard(leave_types: list) -> InlineKeyboardMarkup:
    """Dynamic leave type selection from API data."""
    buttons = []
    for lt in leave_types:
        code = lt.get("code", "")
        name = lt.get("name", code)
        paid = " (có lương)" if lt.get("isPaid") else " (không lương)"
        buttons.append([InlineKeyboardButton(f"📋 {name}{paid}", callback_data=f"leavetype_{code}")])
    buttons.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="back_to_type")])
    return InlineKeyboardMarkup(buttons)


def trip_type_keyboard() -> InlineKeyboardMarkup:
    """Business trip type selection."""
    buttons = []
    for code, label in TRIP_TYPES.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"triptype_{code}")])
    buttons.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="back_to_type")])
    return InlineKeyboardMarkup(buttons)


def trip_reason_keyboard() -> InlineKeyboardMarkup:
    """Business trip reason selection."""
    buttons = []
    for code, label in TRIP_REASONS.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"tripreason_{code}")])
    return InlineKeyboardMarkup(buttons)


def transport_method_keyboard() -> InlineKeyboardMarkup:
    """Transport method selection."""
    buttons = []
    for code, label in TRANSPORT_METHODS.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"transport_{code}")])
    return InlineKeyboardMarkup(buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirm or cancel."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Xác nhận", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Hủy", callback_data="confirm_no"),
        ]
    ])


def approval_action_keyboard(app_id: str) -> InlineKeyboardMarkup:
    """Approve / Reject / Detail buttons for a specific application."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt", callback_data=f"approve_{app_id}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"reject_{app_id}"),
        ],
        [InlineKeyboardButton("📄 Chi tiết", callback_data=f"detail_{app_id}")],
    ])


def pagination_keyboard(current_page: int, total_pages: int, prefix: str = "page") -> InlineKeyboardMarkup:
    """Navigation for paginated lists."""
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"{prefix}_{current_page - 1}"))
    buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton("Sau ➡️", callback_data=f"{prefix}_{current_page + 1}"))
    return InlineKeyboardMarkup([buttons]) if buttons else InlineKeyboardMarkup([])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Single button to go back to menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu chính", callback_data="menu_main")],
    ])


def my_app_keyboard(app_id: str, status: str) -> InlineKeyboardMarkup:
    """Per-application keyboard in the my-apps list.
    Shows a cancel button only when the status allows cancellation.
    """
    cancellable = status in ("PENDING", "IN_PROGRESS")
    buttons = []
    if cancellable:
        buttons.append(
            InlineKeyboardButton("🗑 Hủy đơn", callback_data=f"cancelapp_{app_id}")
        )
    if buttons:
        return InlineKeyboardMarkup([buttons])
    return InlineKeyboardMarkup([])
