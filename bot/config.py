"""Configuration module — loads environment variables and defines constants."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── ERP API ───────────────────────────────────────────────────────────────────
ERP_BASE_URL: str = os.getenv("ERP_BASE_URL", "https://staging-erp.twendeesoft.com")

# ── Google OAuth ──────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

# ── Optional admin token for Feature 3 ────────────────────────────────────────
BOT_ADMIN_TOKEN: str = os.getenv("BOT_ADMIN_TOKEN", "")

# ── Gemini AI ─────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "bear_bot.db")

# ── API Endpoint Paths ───────────────────────────────────────────────────────
API = {
    # Auth
    "login": "/api/auth/login",
    "google_auth": "/api/auth/google",
    "google_callback": "/api/auth/google/callback",
    "profile": "/api/auth/profile",
    "refresh_token": "/api/auth/refresh-token",
    "logout": "/api/auth/logout",

    # Applications
    "time_applications": "/api/application/time-applications",
    "my_applications": "/api/application/time-applications/my",
    "application_detail": "/api/application/time-applications/{id}/detail",
    "approve_application": "/api/application/time-applications/{id}/approve",
    "reject_application": "/api/application/time-applications/{id}/reject",
    "cancel_application": "/api/application/time-applications/{id}/cancel",
    "bulk_approve": "/api/application/time-applications/approve/bulk",
    "potential_approvers": "/api/application/time-applications/potential-approvers",

    # Leave Types
    "leave_types_active": "/api/config/leave-types/active",

    # Users
    "employees": "/api/hr/employees",
    "employee_profile": "/api/hr/profile/{id}",
    "employee_status": "/api/hr/profile/{id}/status",

    # User Links
    "user_links": "/api/user-links",
    "user_links_by_user": "/api/user-links/user/{userId}",
    "user_links_me": "/api/user-links/me/links",
}

# ── Application Types ────────────────────────────────────────────────────────
APPLICATION_TYPES = {
    "LEAVE": "🏖️ Nghỉ phép",
    "OVERTIME": "⏰ Tăng ca",
    "BUSINESS_TRIP": "✈️ Công tác",
    "CHECKIN": "📋 Chấm công",
}

APPLICATION_STATUSES = {
    "PENDING": "🟡 Chờ duyệt",
    "IN_PROGRESS": "🔵 Đang xử lý",
    "APPROVED": "🟢 Đã duyệt",
    "REJECTED": "🔴 Từ chối",
    "COMPLETED": "✅ Hoàn thành",
    "CANCELLED": "⚫ Đã hủy",
}

TRIP_TYPES = {
    "DOMESTIC": "🇻🇳 Nội địa",
    "INTERNATIONAL": "🌍 Quốc tế",
    "INTERNAL": "🏢 Nội bộ",
}

TRIP_REASONS = {
    "CONFERENCE": "📊 Hội nghị",
    "CLIENT": "🤝 Khách hàng",
    "OTHER": "📝 Khác",
}

TRANSPORT_METHODS = {
    "PERSONAL": "🚗 Cá nhân",
    "BOOKED": "🎫 Đặt vé",
}

# ── Conversation States ──────────────────────────────────────────────────────
# Login flow
(
    LOGIN_ENTER_USERNAME,
    LOGIN_ENTER_PASSWORD,
) = range(200, 202)

# Feature 1: Create Application
(
    SELECT_APP_TYPE,
    SELECT_LEAVE_TYPE,
    ENTER_START_DATE,
    ENTER_END_DATE,
    ENTER_REASON,
    ENTER_DESCRIPTION,
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
) = range(18)

# Feature 2: Approve Application
(
    APPROVE_LIST,
    APPROVE_ACTION,
    ENTER_REJECT_REASON,
) = range(100, 103)

# Feature 4: AI Report
(
    REPORT_WAITING_INPUT,
) = range(300, 301)
