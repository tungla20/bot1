"""Message formatters — build rich text messages from API data."""

from datetime import datetime
from typing import Any, Dict, Optional

from bot.config import APPLICATION_TYPES, APPLICATION_STATUSES, TRIP_TYPES, TRIP_REASONS, TRANSPORT_METHODS


def status_emoji(status: str) -> str:
    return APPLICATION_STATUSES.get(status, f"❓ {status}")


def app_type_label(app_type: str) -> str:
    return APPLICATION_TYPES.get(app_type, app_type)


def format_date(dt_str: Optional[str]) -> str:
    """Format ISO datetime string to Vietnamese DD/MM/YYYY."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return dt_str


def format_datetime(dt_str: Optional[str]) -> str:
    """Format ISO datetime string to Vietnamese DD/MM/YYYY HH:MM."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, AttributeError):
        return dt_str


def format_application_summary(app: Dict[str, Any]) -> str:
    """One-line summary of an application for list views."""
    app_type = app_type_label(app.get("type", ""))
    status = status_emoji(app.get("status", ""))
    reason = app.get("reason", "")
    created = format_date(app.get("createdAt", ""))

    # Employee info (for approvers viewing others' apps)
    employee = app.get("employee", {}) or {}
    emp_name = employee.get("fullName", "")
    if not emp_name:
        user = app.get("user", {}) or {}
        emp_name = f'{user.get("firstName", "")} {user.get("lastName", "")}'.strip()

    lines = [f"{app_type} — {status}"]
    if emp_name:
        lines[0] = f"{app_type} — {emp_name}\n{status}"
    if reason:
        lines.append(f"📝 {reason[:80]}")
    lines.append(f"📅 {created}")

    return "\n".join(lines)


def format_application_detail(app: Dict[str, Any]) -> str:
    """Detailed multi-line view of an application."""
    app_type = app_type_label(app.get("type", ""))
    status = status_emoji(app.get("status", ""))
    reason = app.get("reason", "Không có")
    description = app.get("description", "")
    created = format_datetime(app.get("createdAt", ""))

    # Employee info
    employee = app.get("employee", {}) or {}
    emp_name = employee.get("fullName", "")
    emp_dept = employee.get("department", "")
    if not emp_name:
        user = app.get("user", {}) or {}
        emp_name = f'{user.get("firstName", "")} {user.get("lastName", "")}'.strip()

    lines = [
        f"{'═' * 30}",
        f"📋 <b>{app_type}</b>",
        f"📊 Trạng thái: {status}",
    ]

    if emp_name:
        lines.append(f"👤 Nhân viên: {emp_name}")
    if emp_dept:
        lines.append(f"🏢 Phòng ban: {emp_dept}")

    lines.append(f"📝 Lý do: {reason}")
    if description:
        lines.append(f"📄 Mô tả: {description}")

    # Type-specific details
    app_type_code = app.get("type", "")

    if app_type_code == "LEAVE":
        leave_dates = app.get("leaveDates", [])
        leave_type_info = app.get("leaveTypeConfig", {}) or {}
        leave_type_name = leave_type_info.get("name", app.get("leaveType", ""))
        if leave_type_name:
            lines.append(f"🏖️ Loại nghỉ: {leave_type_name}")
        if leave_dates:
            for ld in leave_dates:
                start = format_datetime(ld.get("startTime"))
                end = format_datetime(ld.get("endTime"))
                days = ld.get("days", "")
                day_str = f" ({days} ngày)" if days else ""
                lines.append(f"  📅 {start} → {end}{day_str}")

    elif app_type_code == "OVERTIME":
        ot_details = app.get("overtimeDetails", [])
        for ot in ot_details:
            ot_date = format_date(ot.get("otDate"))
            start = format_datetime(ot.get("startTime"))
            end = format_datetime(ot.get("endTime"))
            hours = ot.get("hours", "")
            hour_str = f" ({hours}h)" if hours else ""
            note = ot.get("note", "")
            lines.append(f"  ⏰ {ot_date}: {start} → {end}{hour_str}")
            if note:
                lines.append(f"     📝 {note}")

    elif app_type_code == "BUSINESS_TRIP":
        bt = app.get("businessTripDetails", {}) or {}
        if bt:
            trip_type = TRIP_TYPES.get(bt.get("tripType", ""), bt.get("tripType", ""))
            location = bt.get("location", "")
            reason_code = bt.get("reason", "")
            trip_reason = TRIP_REASONS.get(reason_code, reason_code)
            transport = TRANSPORT_METHODS.get(bt.get("transportMethod", ""), bt.get("transportMethod", ""))
            start = format_datetime(bt.get("startTime"))
            end = format_datetime(bt.get("endTime"))
            lines.append(f"  ✈️ Loại: {trip_type}")
            lines.append(f"  📅 {start} → {end}")
            if location:
                lines.append(f"  📍 Địa điểm: {location}")
            if trip_reason:
                lines.append(f"  💼 Lý do: {trip_reason}")
            if transport:
                lines.append(f"  🚗 Phương tiện: {transport}")

    elif app_type_code == "CHECKIN":
        checkin_details = app.get("checkinDetails", [])
        for ci in checkin_details:
            check_time = format_datetime(ci.get("checkTime"))
            ci_reason = ci.get("reason", "")
            lines.append(f"  📋 Thời gian: {check_time}")
            if ci_reason:
                lines.append(f"     📝 Lý do: {ci_reason}")

    # Approvals
    approvals = app.get("approvals", [])
    if approvals:
        lines.append(f"\n👥 <b>Người duyệt:</b>")
        for a in approvals:
            approver = a.get("approver", {}) or {}
            approver_name = approver.get("firstName", "") + " " + approver.get("lastName", "")
            approver_name = approver_name.strip() or "N/A"
            a_status = status_emoji(a.get("status", ""))
            comments = a.get("comments", "")
            line = f"  {a_status} {approver_name}"
            if comments:
                line += f" — {comments}"
            lines.append(line)

    lines.append(f"\n🕐 Tạo lúc: {created}")
    lines.append(f"{'═' * 30}")

    return "\n".join(lines)


def format_application_card_for_approval(app: Dict[str, Any]) -> str:
    """Compact card shown in the approval list."""
    app_type = app_type_label(app.get("type", ""))
    reason = app.get("reason", "Không có lý do")

    employee = app.get("employee", {}) or {}
    emp_name = employee.get("fullName", "")
    if not emp_name:
        user = app.get("user", {}) or {}
        emp_name = f'{user.get("firstName", "")} {user.get("lastName", "")}'.strip() or "N/A"

    # Date range
    date_info = ""
    app_type_code = app.get("type", "")
    if app_type_code == "LEAVE":
        leave_dates = app.get("leaveDates", [])
        if leave_dates:
            first = format_date(leave_dates[0].get("startTime"))
            last = format_date(leave_dates[-1].get("endTime"))
            date_info = f"📅 {first} → {last}"
    elif app_type_code == "OVERTIME":
        ot_details = app.get("overtimeDetails", [])
        if ot_details:
            date_info = f"📅 {format_date(ot_details[0].get('otDate'))}"
    elif app_type_code == "BUSINESS_TRIP":
        bt = app.get("businessTripDetails", {}) or {}
        if bt:
            date_info = f"📅 {format_date(bt.get('startTime'))} → {format_date(bt.get('endTime'))}"

    lines = [
        f"{app_type} — <b>{emp_name}</b>",
    ]
    if date_info:
        lines.append(date_info)
    lines.append(f"📝 {reason[:100]}")

    return "\n".join(lines)


def format_employee_info(employee: Dict[str, Any]) -> str:
    """Employee or User card for account management."""
    # Handle HR Profile format vs direct User format
    name = employee.get("fullName", "")
    if not name:
        first = employee.get("firstName", "")
        last = employee.get("lastName", "")
        name = f"{first} {last}".strip() or "N/A"

    code = employee.get("employeeCode", "N/A")
    dept = employee.get("department", "N/A")
    position = employee.get("position", "N/A")
    status = employee.get("status", "N/A")
    role = employee.get("role", "N/A")
    
    email = employee.get("email", "")
    user = employee.get("user", {}) or {}
    if user and not email:
        email = user.get("email", "N/A")
    elif not email:
        email = "N/A"

    lines = [
        f"{'═' * 30}",
        f"👤 <b>{name}</b>",
        f"📧 Email: {email}",
        f"📊 Trạng thái: {status}",
        f"🔑 Vai trò: {role}",
    ]
    if code != "N/A":
        lines.append(f"🔢 Mã NV: {code}")
    if dept != "N/A" and dept:
        lines.append(f"🏢 Phòng ban: {dept}")
    if position != "N/A" and position:
        lines.append(f"💼 Vị trí: {position}")

    lines.append(f"{'═' * 30}")
    return "\n".join(lines)


def format_confirm_application(data: Dict[str, Any]) -> str:
    """Format the application data for confirmation before submission."""
    app_type_code = data.get("type", "")
    app_type = app_type_label(app_type_code)
    reason = data.get("reason", "Không có")

    lines = [
        f"{'═' * 30}",
        f"📋 <b>Xác nhận tạo đơn</b>",
        f"Loại: {app_type}",
        f"Lý do: {reason}",
    ]

    if app_type_code == "LEAVE":
        leave_type = data.get("leaveType", "")
        lines.append(f"🏖️ Loại nghỉ: {leave_type}")
        leave_dates = data.get("leaveDates", [])
        for ld in leave_dates:
            start = ld.get("startTime", "")
            end = ld.get("endTime", "")
            lines.append(f"📅 {start} → {end}")

    elif app_type_code == "OVERTIME":
        ot_details = data.get("overtimeDetails", [])
        for ot in ot_details:
            lines.append(f"⏰ Ngày: {ot.get('otDate', '')}")
            lines.append(f"   {ot.get('startTime', '')} → {ot.get('endTime', '')}")
            if ot.get("note"):
                lines.append(f"   📝 {ot['note']}")

    elif app_type_code == "BUSINESS_TRIP":
        bt = data.get("businessTripDetails", {})
        if bt:
            trip_type = TRIP_TYPES.get(bt.get("tripType", ""), bt.get("tripType", ""))
            lines.append(f"✈️ Loại: {trip_type}")
            lines.append(f"📅 {bt.get('startTime', '')} → {bt.get('endTime', '')}")
            if bt.get("location"):
                lines.append(f"📍 Địa điểm: {bt['location']}")

    elif app_type_code == "CHECKIN":
        checkin_details = data.get("checkinDetails", [])
        for ci in checkin_details:
            lines.append(f"📋 Thời gian: {ci.get('checkTime', '')}")
            if ci.get("reason"):
                lines.append(f"   📝 {ci['reason']}")

    lines.append(f"{'═' * 30}")
    lines.append("\nBạn có muốn gửi đơn này không?")
    return "\n".join(lines)
