"""HTTP client for the ERP REST API.

Wraps httpx.AsyncClient with automatic Bearer token attachment and
transparent token refresh on 401 responses.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from bot.config import ERP_BASE_URL, API
from bot import database

logger = logging.getLogger(__name__)


class ERPClient:
    """Async HTTP client bound to a single Telegram user session."""

    def __init__(self, telegram_chat_id: int):
        self.telegram_chat_id = telegram_chat_id
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _load_tokens(self) -> bool:
        """Load tokens from the database. Returns False if no session."""
        session = await database.get_session(self.telegram_chat_id)
        if session is None:
            return False
        self._access_token = session["access_token"]
        self._refresh_token = session.get("refresh_token", "")
        return True

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{ERP_BASE_URL}{path}"

    async def login_with_credentials(self, username: str, password: str) -> dict:
        """Call POST /api/auth/login and return the full response dict."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._url(API["login"]),
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json"},
            )
        if resp.status_code in (200, 201):
            return resp.json()
        elif resp.status_code == 401:
            raise AuthenticationError("Sai tên đăng nhập hoặc mật khẩu.")
        else:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise AuthenticationError(f"Đăng nhập thất bại ({resp.status_code}): {detail}")

    async def _try_refresh(self) -> bool:
        """Attempt to refresh the access token. Returns True on success."""
        if not self._refresh_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    self._url(API["refresh_token"]),
                    json={"refreshToken": self._refresh_token},
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self._access_token = data.get("access_token", data.get("accessToken", ""))
                    new_refresh = data.get("refresh_token", data.get("refreshToken", ""))
                    await database.update_token(
                        self.telegram_chat_id,
                        self._access_token,
                        new_refresh or self._refresh_token,
                    )
                    logger.info("Token refreshed for chat %s", self.telegram_chat_id)
                    return True
        except Exception as e:
            logger.error("Token refresh failed: %s", e)
        return False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[Dict] = None,
        retry_on_401: bool = True,
    ) -> httpx.Response:
        """Make an authenticated request with automatic token refresh."""
        if self._access_token is None:
            loaded = await self._load_tokens()
            if not loaded:
                raise AuthenticationError("Bạn chưa đăng nhập. Dùng /login để đăng nhập.")

        url = self._url(path)
        logger.debug("REQUEST %s %s | json=%s | params=%s", method, url, json, params)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                url,
                json=json,
                params=params,
                headers=self._headers(),
            )

        logger.debug("RESPONSE %s %s | status=%s | body=%s", method, url, resp.status_code, resp.text[:500])

        if resp.status_code == 401 and retry_on_401:
            refreshed = await self._try_refresh()
            if refreshed:
                return await self._request(method, path, json=json, params=params, retry_on_401=False)
            raise AuthenticationError("Phiên đăng nhập đã hết hạn. Dùng /login để đăng nhập lại.")

        return resp

    # ── Public API methods ────────────────────────────────────────────────

    # Auth / Profile
    async def get_profile(self) -> Dict[str, Any]:
        resp = await self._request("GET", API["profile"])
        resp.raise_for_status()
        return resp.json()

    # Leave Types
    async def get_leave_types(self) -> list:
        resp = await self._request("GET", API["leave_types_active"])
        resp.raise_for_status()
        return resp.json()

    async def get_potential_approvers(self) -> list:
        """Fetch potential approvers (Manager, HR, Admin, BOD roles)."""
        resp = await self._request("GET", API["potential_approvers"])
        resp.raise_for_status()
        data = resp.json()
        # May return a list or {data: [...]}
        if isinstance(data, list):
            return data
        return data.get("data", data.get("items", []))

    # Time Applications — CRUD
    async def create_time_application(self, data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("CREATE TIME APPLICATION payload: %s", data)
        resp = await self._request("POST", API["time_applications"], json=data)
        logger.info("CREATE TIME APPLICATION response: status=%s body=%s", resp.status_code, resp.text[:1000])
        if resp.status_code in (200, 201):
            return resp.json()
        error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise APIError(f"Tạo đơn thất bại ({resp.status_code}): {error_detail}")

    async def get_my_applications(self, **filters) -> Dict[str, Any]:
        params = {k: v for k, v in filters.items() if v is not None}
        resp = await self._request("GET", API["my_applications"], params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_application_detail(self, app_id: str) -> Dict[str, Any]:
        path = API["application_detail"].replace("{id}", app_id)
        resp = await self._request("GET", path)
        resp.raise_for_status()
        return resp.json()

    # Time Applications — Approval
    async def get_pending_approvals(self, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        resp = await self._request(
            "GET",
            API["time_applications"],
            params={"filterWaitingApproval": "true", "page": page, "limit": limit, "sortOrder": "desc"},
        )
        resp.raise_for_status()
        return resp.json()

    async def approve_application(self, app_id: str, comments: str = "") -> Dict[str, Any]:
        path = API["approve_application"].replace("{id}", app_id)
        body: Dict[str, Any] = {"status": "APPROVED"}
        if comments:
            body["comments"] = comments
        resp = await self._request("POST", path, json=body)
        if resp.status_code in (200, 201):
            return resp.json()
        error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise APIError(f"Duyệt đơn thất bại ({resp.status_code}): {error_detail}")

    async def reject_application(self, app_id: str, comments: str = "") -> Dict[str, Any]:
        path = API["reject_application"].replace("{id}", app_id)
        body: Dict[str, Any] = {}
        if comments:
            body["comments"] = comments
        resp = await self._request("POST", path, json=body)
        if resp.status_code in (200, 201):
            return resp.json()
        error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise APIError(f"Từ chối đơn thất bại ({resp.status_code}): {error_detail}")

    async def cancel_application(self, app_id: str) -> Dict[str, Any]:
        path = API["cancel_application"].replace("{id}", app_id)
        resp = await self._request("POST", path)
        if resp.status_code in (200, 201):
            return resp.json()
        error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise APIError(f"Hủy đơn thất bại ({resp.status_code}): {error_detail}")

    # HR / Employees
    async def get_employees(self, search: str = "", page: int = 1, limit: int = 10) -> Dict[str, Any]:
        params: Dict[str, Any] = {"page": page, "limit": limit}
        if search:
            params["search"] = search
        resp = await self._request("GET", API["employees"], params=params)
        resp.raise_for_status()
        return resp.json()

    async def update_employee_status(self, profile_id: str, status: str) -> Dict[str, Any]:
        path = API["employee_status"].replace("{id}", profile_id)
        resp = await self._request("PUT", path, json={"status": status})
        if resp.status_code in (200, 201):
            return resp.json()
        error_detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise APIError(f"Cập nhật trạng thái thất bại ({resp.status_code}): {error_detail}")


class AuthenticationError(Exception):
    """Raised when the user is not authenticated or token is expired."""
    pass


class APIError(Exception):
    """Raised when an API call fails."""
    pass
