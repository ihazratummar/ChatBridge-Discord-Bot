import os
import re
import time
import logging
import asyncio
import pyotp
from curl_cffi.requests import AsyncSession

logger = logging.getLogger("ChatBridge.F2FClient")

BASE_URL = "https://f2f.com/api"

class F2FClient:
    def __init__(self, username: str | None = None, password: str | None = None,
                 totp_secret: str | None = None, session_id: str | None = None,
                 csrf_token: str | None = None, event_callback=None):
        self.username = username or os.getenv("F2F_USERNAME")
        self.password = password or os.getenv("F2F_PASSWORD")
        self.totp_secret = totp_secret or os.getenv("F2F_TOTP_SECRET")
        self.session_id = session_id or os.getenv("F2F_SESSION_ID", "")
        self.csrf_token = csrf_token or os.getenv("F2F_CSRF_TOKEN", "")
        self.session: AsyncSession | None = None
        self._global_send_lock = asyncio.Lock()
        self._login_lock = asyncio.Lock()
        self._min_send_gap_seconds = 4.0  # Enforces 4s minimum spacing between ANY outgoing API calls across all creators!
        self._last_send_timestamp = 0.0
        self._last_login_timestamp = 0.0
        self._last_login_failed_at = 0.0
        self.event_callback = event_callback

    async def _notify_event(self, title: str, description: str, level: str = "info"):
        if self.event_callback:
            try:
                res = self.event_callback(title, description, level)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.warning(f"Error executing event_callback: {e}")

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
        """Autonomous 2FA login with step-by-step tracing and audit log dispatch to #f2f_logs."""
        async with self._login_lock:
            now_ts = asyncio.get_event_loop().time()

            # Dedup: If another parallel task SUCCESSFULLY refreshed within 10s, skip
            if (now_ts - self._last_login_timestamp) < 10.0 and self.session_id:
                logger.info("⚡ F2F session was recently refreshed by a parallel task. Skipping duplicate login.")
                return True

            # Dedup: If a login just FAILED within 30s, don't hammer F2F again
            if (now_ts - self._last_login_failed_at) < 30.0:
                logger.warning("⚡ F2F login recently failed. Waiting 30s before retry to avoid rate limits.")
                return False

            if not self.username or not self.password:
                err_msg = "F2F_USERNAME or F2F_PASSWORD environment variable is missing."
                logger.error(err_msg)
                await self._notify_event("Login Failed: Credentials Missing", f"• Account: `{self.username or 'None'}`\n• Error: {err_msg}", level="error")
                return False

            last_rejected_otp = None  # Track burned TOTP codes to avoid reuse
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                await self._ensure_session()
                logger.info(f"🔑 Step 1/4: Initiating autonomous login (Attempt {attempt}/{max_attempts}) for '{self.username}'...")

                try:
                    # Step 1: GET /login/ to retrieve initial CSRF token
                    get_resp = await self.session.get("https://f2f.com/login/", headers=self._get_headers())

                    # Try resp.cookies first, then fall back to session cookie jar
                    csrf_found = False
                    if "csrftoken" in get_resp.cookies:
                        self.csrf_token = get_resp.cookies["csrftoken"]
                        csrf_found = True
                    elif hasattr(self.session, "cookies") and "csrftoken" in self.session.cookies:
                        self.csrf_token = self.session.cookies["csrftoken"]
                        csrf_found = True

                    if csrf_found:
                        logger.info(f"🔑 Step 1/4 Complete: Initial CSRF Token extracted ({self.csrf_token[:8]}...).")
                    else:
                        logger.warning("Step 1/4 Warning: CSRF token not found on login page, proceeding...")

                    # Step 2: Generate 2FA TOTP code (wait for fresh code if previous was rejected)
                    login_url = f"{BASE_URL}/auth/login/"
                    otp_code = None
                    if self.totp_secret:
                        try:
                            totp = pyotp.TOTP(self.totp_secret)
                            otp_code = totp.at(int(time.time()))  # UTC-safe, works on any timezone/VPS

                            # If this code was already rejected by F2F, wait for TOTP window rotation
                            if last_rejected_otp and otp_code == last_rejected_otp:
                                logger.info(f"🔑 Step 2/4: TOTP code {otp_code} was already burned. Waiting for 30s window rotation...")
                                for _ in range(35):  # Max 35 seconds wait
                                    await asyncio.sleep(1)
                                    otp_code = totp.at(int(time.time()))  # UTC-safe, works on any timezone/VPS
                                    if otp_code != last_rejected_otp:
                                        break
                                if otp_code == last_rejected_otp:
                                    logger.error("Step 2/4: TOTP window did not rotate after 35s. Aborting login.")
                                    self._last_login_failed_at = asyncio.get_event_loop().time()
                                    return False

                            logger.info(f"🔑 Step 2/4: Generated fresh 2FA OTP code ({otp_code}) via pyotp.")
                        except Exception as e:
                            logger.warning(f"Step 2/4 Warning: Failed to generate pyotp TOTP code: {e}")
                    else:
                        logger.warning("Step 2/4 Warning: F2F_TOTP_SECRET missing in configuration.")

                    payload = {
                        "email": self.username,
                        "username": self.username,
                        "password": self.password
                    }
                    if otp_code:
                        payload["otp_token"] = otp_code
                        payload["code"] = otp_code

                    # Step 3: POST /auth/login/
                    logger.info(f"🔑 Step 3/4: Submitting authentication payload to {login_url}...")
                    resp = await self.session.post(login_url, json=payload, headers=self._get_headers(), cookies=self._get_cookies())
                    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

                    if resp.status_code in (200, 202) and (data.get("requires_2fa") or "verify_login" in str(data)):
                        logger.info("🔑 Step 3.5/4: Secondary 2FA verification required by F2F.")
                        # Extract interim cookies from Step 3 login response BEFORE verify call
                        self._extract_cookies_from_response(resp)

                        if not self.totp_secret:
                            err_msg = "F2F_TOTP_SECRET missing! Cannot auto-complete secondary 2FA."
                            logger.error(err_msg)
                            await self._notify_event("2FA Login Failed", f"• Account: `{self.username}`\n• Error: {err_msg}", level="error")
                            self._last_login_failed_at = asyncio.get_event_loop().time()
                            return False

                        totp = pyotp.TOTP(self.totp_secret)
                        otp_code = totp.at(int(time.time()))  # UTC-safe, works on any timezone/VPS

                        verify_url = f"{BASE_URL}/auth/verify_login/"
                        verify_payload = {"code": otp_code}

                        verify_resp = await self.session.post(verify_url, json=verify_payload, headers=self._get_headers(), cookies=self._get_cookies())
                        if verify_resp.status_code == 200:
                            self._extract_cookies_from_response(verify_resp)
                            self._last_login_timestamp = asyncio.get_event_loop().time()
                            logger.info("🎉 Step 4/4 Complete: Autonomous 2FA Login Successful!")
                            await self._notify_event(
                                "Autonomous F2F Session Refreshed",
                                f"• Account: **{self.username}**\n• Status: Successfully logged in via 2FA TOTP!\n• Session ID: `{self.session_id[:10]}...`",
                                level="success"
                            )
                            return True
                        else:
                            last_rejected_otp = otp_code
                            if attempt < max_attempts:
                                logger.warning(f"Secondary 2FA verification attempt {attempt} failed. Will retry with fresh TOTP...")
                                continue
                            err_msg = f"2FA verification failed (HTTP {verify_resp.status_code}): {verify_resp.text[:150]}"
                            logger.error(err_msg)
                            await self._notify_event("2FA Login Failed", f"• Account: `{self.username}`\n• Error: {err_msg}", level="error")
                            self._last_login_failed_at = asyncio.get_event_loop().time()
                            return False

                    elif resp.status_code == 200:
                        self._extract_cookies_from_response(resp)
                        self._last_login_timestamp = asyncio.get_event_loop().time()
                        logger.info("🎉 Step 4/4 Complete: Autonomous Login Successful!")
                        await self._notify_event(
                            "Autonomous F2F Session Refreshed",
                            f"• Account: **{self.username}**\n• Status: Successfully logged into F2F!\n• Session ID: `{self.session_id[:10]}...`",
                            level="success"
                        )
                        return True
                    else:
                        is_otp_boundary_err = "invalid-otp-token" in str(data).lower()
                        if is_otp_boundary_err:
                            last_rejected_otp = otp_code  # Mark this code as burned
                            if attempt < max_attempts:
                                logger.warning(f"🔑 TOTP code {otp_code} rejected on attempt {attempt}. Will wait for fresh TOTP window...")
                                continue

                        friendly_reason = self._format_friendly_error(resp.status_code, str(data))
                        logger.error(f"Login failed (HTTP {resp.status_code}): {data}")
                        await self._notify_event(
                            "F2F Login Failed",
                            f"• Account: `{self.username}`\n• Status Code: `HTTP {resp.status_code}`\n• Reason: {friendly_reason}",
                            level="error"
                        )
                        self._last_login_failed_at = asyncio.get_event_loop().time()
                        return False
                except Exception as e:
                    if attempt < max_attempts:
                        logger.warning(f"Network exception on login attempt {attempt}: {e}. Retrying in 2s...")
                        await asyncio.sleep(2)
                        continue
                    err_msg = f"Network connection error during login: {e}"
                    logger.error(err_msg, exc_info=True)
                    await self._notify_event("F2F Login Network Error", f"• Account: `{self.username}`\n• Error: {err_msg}", level="error")
                    self._last_login_failed_at = asyncio.get_event_loop().time()
                    return False

        self._last_login_failed_at = asyncio.get_event_loop().time()
        return False

    def _extract_cookies_from_response(self, resp):
        cookies = resp.cookies
        updated = []
        if "sessionid" in cookies:
            self.session_id = cookies["sessionid"]
            updated.append(f"Session ID: {self.session_id[:10]}...")
        if "csrftoken" in cookies:
            self.csrf_token = cookies["csrftoken"]
            updated.append(f"CSRF Token: {self.csrf_token[:10]}...")
        if updated:
            logger.info(f"🍪 Extracted cookies: {' | '.join(updated)}")
        else:
            logger.warning("⚠️ No sessionid or csrftoken found in response cookies.")

    async def get_online_chats(self, creator: str, max_pages: int = 10, auto_retry: bool = True) -> list[dict]:
        """Fetches all online chats for creator by traversing F2F API pagination cursor ('next')."""
        await self._ensure_session()
        all_chats = []
        next_url = f"{BASE_URL}/chats/?ordering=oldest-unread-payment-first&filters=only-online"
        page_count = 0

        while next_url and page_count < max_pages:
            page_count += 1
            headers = self._get_headers(creator)
            cookies = self._get_cookies()

            try:
                resp = await self.session.get(next_url, headers=headers, cookies=cookies)
                if resp.status_code in (401, 403) and auto_retry and page_count == 1:
                    logger.warning(f"Got {resp.status_code} for creator @{creator}. Attempting autonomous session refresh...")
                    if await self.refresh_session():
                        return await self.get_online_chats(creator, max_pages=max_pages, auto_retry=False)
                    else:
                        logger.error(f"Authentication failed ({resp.status_code}) for creator @{creator}.")
                        return []

                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        page_chats = data.get("results", [])
                        if isinstance(page_chats, list):
                            all_chats.extend(page_chats)
                        next_url = data.get("next")
                    elif isinstance(data, list):
                        all_chats.extend(data)
                        next_url = None
                    else:
                        next_url = None
                else:
                    logger.error(f"Failed to fetch online chats page {page_count} ({resp.status_code}): {resp.text[:200]}")
                    break
            except Exception as e:
                logger.error(f"HTTP Error fetching online chats page {page_count} for @{creator}: {e}", exc_info=True)
                break

        logger.info(f"Total online chats fetched for creator @{creator}: {len(all_chats)} across {page_count} page(s).")
        return all_chats

    async def validate_creator_exists(self, creator: str, auto_retry: bool = True) -> bool:
        """Verifies whether the given creator handle exists and is authorized on F2F."""
        await self._ensure_session()
        url = f"{BASE_URL}/chats/?limit=1"
        headers = self._get_headers(creator)
        cookies = self._get_cookies()

        try:
            resp = await self.session.get(url, headers=headers, cookies=cookies)
            if resp.status_code in (401, 403) and auto_retry:
                if await self.refresh_session():
                    return await self.validate_creator_exists(creator, auto_retry=False)
                return False

            if resp.status_code == 200:
                return True
            else:
                logger.warning(f"Creator validation failed for @{creator} (HTTP {resp.status_code})")
                return False
        except Exception as e:
            logger.error(f"HTTP Error validating creator @{creator}: {e}")
            return False

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

    async def get_chat_summary(self, chat_id: str, creator: str) -> dict | None:
        """
        Fetches the chat summary dictionary from the general chats list (GET /chats/) WITHOUT calling GET /chats/{chat_id}/.
        This GUARANTEES that unread status and red notification badges on F2F remain 100% untouched!
        """
        recent_chats = await self.get_recent_chats(creator)
        for chat in recent_chats:
            if isinstance(chat, dict):
                c_uuid = str(chat.get("uuid") or chat.get("id") or "")
                if c_uuid == str(chat_id):
                    return chat
        return None

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

    def _format_friendly_error(self, status_code: int, raw_text: str, creator: str = "", chat_id: str = "") -> str:
        """Translates technical HTTP status codes into friendly plain-English messages for non-developer managers."""
        if status_code == 404:
            return f"Chat UUID '{chat_id}' not found or does not belong to creator @{creator} on F2F."
        elif status_code in (401, 403):
            return f"F2F session expired or unauthorized for creator @{creator}."
        elif status_code == 429:
            return "F2F server rate limit reached. Pacing automatically..."
        elif status_code >= 500:
            return f"F2F server is temporarily busy or undergoing maintenance (HTTP {status_code})."
        else:
            return f"F2F request error (HTTP {status_code}): {raw_text[:100]}"

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
            async with self._global_send_lock:
                # Enforce global agency rate control across all creator models!
                now = asyncio.get_event_loop().time()
                elapsed = now - self._last_send_timestamp
                if elapsed < self._min_send_gap_seconds:
                    await asyncio.sleep(self._min_send_gap_seconds - elapsed)

                resp = await self.session.post(url, json=payload, headers=headers, cookies=cookies)
                self._last_send_timestamp = asyncio.get_event_loop().time()

            if resp.status_code in (401, 403) and auto_retry:
                logger.warning(f"Got {resp.status_code} sending message to {chat_id}. Attempting session refresh...")
                if await self.refresh_session():
                    return await self.send_message(chat_id, creator, content, price, reply_to, auto_retry=False)
                else:
                    logger.error(f"Authentication failed ({resp.status_code}) sending message to chat {chat_id}.")
                    return {"error": True, "reason": f"F2F login session expired for creator @{creator}.", "status_code": resp.status_code}

            if resp.status_code in (200, 201):
                res_data = resp.json()
                logger.info(f"✅ Sent message to chat {chat_id} on behalf of creator @{creator}.")
                return res_data
            else:
                friendly_reason = self._format_friendly_error(resp.status_code, resp.text, creator, chat_id)
                logger.error(f"Failed to send message ({resp.status_code}): {friendly_reason}")
                return {"error": True, "reason": friendly_reason, "status_code": resp.status_code}
        except Exception as e:
            friendly_err = f"Network connection to F2F timed out or failed: {e}"
            logger.error(f"HTTP Error sending message to chat {chat_id}: {e}", exc_info=True)
            return {"error": True, "reason": friendly_err}
