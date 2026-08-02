import os
import re
import logging
import asyncio
import pyotp
from curl_cffi.requests import AsyncSession

logger = logging.getLogger("ChatBridge.F2FClient")

BASE_URL = "https://f2f.com/api"

class F2FClient:
    def __init__(self, username: str | None = None, password: str | None = None,
                 totp_secret: str | None = None, session_id: str | None = None,
                 csrf_token: str | None = None):
        self.username = username or os.getenv("F2F_USERNAME")
        self.password = password or os.getenv("F2F_PASSWORD")
        self.totp_secret = totp_secret or os.getenv("F2F_TOTP_SECRET")
        self.session_id = session_id or os.getenv("F2F_SESSION_ID", "")
        self.csrf_token = csrf_token or os.getenv("F2F_CSRF_TOKEN", "")
        self.session: AsyncSession | None = None

    def _get_headers(self, creator: str | None = None) -> dict:
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-IN,en;q=0.9,bn-IN;q=0.8,bn;q=0.7,en-GB;q=0.6,en-US;q=0.5",
            "dnt": "1",
            "priority": "u=1, i",
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        }
        if creator:
            clean_creator = re.sub(r'[^\x00-\x7F]+', '', creator).lower().replace("#", "").strip()
            headers["impersonate-user"] = clean_creator
            headers["referer"] = f"https://f2f.com/agency/creators/{clean_creator}/messenger/"
        if self.csrf_token:
            headers["x-csrftoken"] = self.csrf_token
        return headers

    def _get_cookies(self) -> dict:
        cookies = {}
        if self.session_id:
            cookies["sessionid"] = self.session_id
        if self.csrf_token:
            cookies["csrftoken"] = self.csrf_token
        return cookies

    async def _ensure_session(self):
        if self.session is None:
            self.session = AsyncSession(impersonate="chrome120")

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def refresh_session(self) -> bool:
        """Autonomous 2FA login using stored username, password, and pyotp TOTP secret."""
        if not self.username or not self.password:
            logger.error("Cannot auto-refresh session: F2F_USERNAME or F2F_PASSWORD missing!")
            return False

        await self._ensure_session()
        logger.info(f"Initiating autonomous login for {self.username}...")

        try:
            get_resp = await self.session.get("https://f2f.com/login/", headers=self._get_headers())
            cookies = get_resp.cookies
            if "csrftoken" in cookies:
                self.csrf_token = cookies["csrftoken"]
        except Exception as e:
            logger.warning(f"Initial GET login page failed: {e}")

        login_url = f"{BASE_URL}/auth/login/"
        payload = {
            "username": self.username,
            "password": self.password
        }

        try:
            resp = await self.session.post(login_url, json=payload, headers=self._get_headers())
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

            if resp.status_code in (200, 202) and (data.get("requires_2fa") or "verify_login" in str(data)):
                logger.info("2FA required by F2F. Generating OTP code in memory via pyotp...")

                if not self.totp_secret:
                    logger.error("F2F_TOTP_SECRET missing! Cannot auto-complete 2FA.")
                    return False

                totp = pyotp.TOTP(self.totp_secret)
                otp_code = totp.now()
                logger.info(f"Generated 2FA OTP Code: {otp_code}")

                verify_url = f"{BASE_URL}/auth/verify_login/"
                verify_payload = {"code": otp_code}

                verify_resp = await self.session.post(verify_url, json=verify_payload, headers=self._get_headers())
                if verify_resp.status_code == 200:
                    self._extract_cookies_from_response(verify_resp)
                    logger.info("🎉 Autonomous TOTP 2FA Login Successful!")
                    return True
                else:
                    logger.error(f"2FA Verification Failed ({verify_resp.status_code}): {verify_resp.text}")
                    return False
            elif resp.status_code == 200:
                self._extract_cookies_from_response(resp)
                logger.info("🎉 Login Successful!")
                return True
            else:
                logger.error(f"Login failed ({resp.status_code}): {data}")
                return False
        except Exception as e:
            logger.error(f"Error during autonomous session refresh: {e}", exc_info=True)
            return False

    def _extract_cookies_from_response(self, resp):
        cookies = resp.cookies
        if "sessionid" in cookies:
            self.session_id = cookies["sessionid"]
        if "csrftoken" in cookies:
            self.csrf_token = cookies["csrftoken"]
        logger.info(f"Updated Session ID: {self.session_id[:10]}... | CSRF Token: {self.csrf_token[:10]}...")

    async def get_online_chats(self, creator: str, auto_retry: bool = True) -> list[dict]:
        """Fetches list of online chats for creator."""
        await self._ensure_session()
        url = f"{BASE_URL}/chats/?ordering=oldest-unread-payment-first&filters=only-online"
        headers = self._get_headers(creator)
        cookies = self._get_cookies()

        try:
            resp = await self.session.get(url, headers=headers, cookies=cookies)
            if resp.status_code in (401, 403) and auto_retry:
                logger.warning(f"Got {resp.status_code} for creator @{creator}. Attempting autonomous session refresh...")
                if await self.refresh_session():
                    return await self.get_online_chats(creator, auto_retry=False)
                else:
                    logger.error(f"Authentication failed ({resp.status_code}) for creator @{creator}.")
                    return []

            if resp.status_code == 200:
                data = resp.json()
                chats = data.get("results", data) if isinstance(data, dict) else data
                logger.info(f"Fetched {len(chats)} online chats for creator @{creator}.")
                return chats
            else:
                logger.error(f"Failed to fetch online chats ({resp.status_code}): {resp.text[:200]}")
                return []
        except Exception as e:
            logger.error(f"HTTP Error fetching online chats: {e}", exc_info=True)
            return []

    async def get_recent_chats(self, creator: str, auto_retry: bool = True) -> list[dict]:
        """Fetches list of recent chats for creator."""
        await self._ensure_session()
        url = f"{BASE_URL}/chats/"
        headers = self._get_headers(creator)
        cookies = self._get_cookies()

        try:
            resp = await self.session.get(url, headers=headers, cookies=cookies)
            if resp.status_code in (401, 403) and auto_retry:
                if await self.refresh_session():
                    return await self.get_recent_chats(creator, auto_retry=False)

            if resp.status_code == 200:
                data = resp.json()
                chats = data.get("results", data) if isinstance(data, dict) else data
                return chats
            return []
        except Exception as e:
            logger.error(f"HTTP Error fetching recent chats for creator @{creator}: {e}", exc_info=True)
            return []

    async def get_chat_details(self, chat_id: str, creator: str, auto_retry: bool = True) -> dict | None:
        """Fetches chat metadata details (title, user info) for a specific chat ID."""
        await self._ensure_session()
        url = f"{BASE_URL}/chats/{chat_id}/"
        headers = self._get_headers(creator)
        cookies = self._get_cookies()

        try:
            resp = await self.session.get(url, headers=headers, cookies=cookies)
            if resp.status_code in (401, 403) and auto_retry:
                if await self.refresh_session():
                    return await self.get_chat_details(chat_id, creator, auto_retry=False)

            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"HTTP Error fetching chat details for {chat_id}: {e}", exc_info=True)
            return None

    async def get_chat_messages(self, chat_id: str, creator: str, auto_retry: bool = True) -> list[dict]:
        """Fetches message history for a specific chat ID."""
        await self._ensure_session()
        url = f"{BASE_URL}/chats/{chat_id}/messages/"
        headers = self._get_headers(creator)
        cookies = self._get_cookies()

        try:
            resp = await self.session.get(url, headers=headers, cookies=cookies)
            if resp.status_code in (401, 403) and auto_retry:
                logger.warning(f"Got {resp.status_code} fetching chat {chat_id}. Attempting session refresh...")
                if await self.refresh_session():
                    return await self.get_chat_messages(chat_id, creator, auto_retry=False)
                else:
                    logger.error(f"Authentication failed ({resp.status_code}) for chat {chat_id}.")
                    return []

            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("results", data) if isinstance(data, dict) else data
                return messages
            else:
                logger.error(f"Failed to fetch chat messages ({resp.status_code}): {resp.text[:200]}")
                return []
        except Exception as e:
            logger.error(f"HTTP Error fetching chat messages: {e}", exc_info=True)
            return []

    async def send_message(self, chat_id: str, creator: str, content: str,
                           price: float | None = None, reply_to: str | None = None,
                           auto_retry: bool = True) -> dict | None:
        """Posts outgoing message to target chat ID."""
        await self._ensure_session()
        url = f"{BASE_URL}/chats/{chat_id}/messages/"
        headers = self._get_headers(creator)
        cookies = self._get_cookies()

        payload = {
            "content": content,
            "price": price,
            "reply_to": reply_to
        }

        try:
            resp = await self.session.post(url, json=payload, headers=headers, cookies=cookies)
            if resp.status_code in (401, 403) and auto_retry:
                logger.warning(f"Got {resp.status_code} sending message to {chat_id}. Attempting session refresh...")
                if await self.refresh_session():
                    return await self.send_message(chat_id, creator, content, price, reply_to, auto_retry=False)
                else:
                    logger.error(f"Authentication failed ({resp.status_code}) sending message to chat {chat_id}.")
                    return None

            if resp.status_code in (200, 201):
                res_data = resp.json()
                logger.info(f"✅ Sent message to chat {chat_id} on behalf of creator @{creator}.")
                return res_data
            else:
                logger.error(f"Failed to send message ({resp.status_code}): {resp.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"HTTP Error sending message to chat {chat_id}: {e}", exc_info=True)
            return None
