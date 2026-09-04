"""
F2F Live Stream Automation & Creator Multi-Account Service.
Uses the battle-tested 4-step authentication engine from ChatBridge F2FClient
(CSRF bootstrap -> Payload submission -> Secondary 2FA verification -> Cookie management).
"""

import asyncio
import logging
import os
import time
from typing import Dict, Optional
from curl_cffi.requests import AsyncSession
import pyotp

logger = logging.getLogger("FastAPI-F2FLive")

BASE_URL = os.getenv("F2F_BASE_URL", "https://f2f.com/api")

class F2FLiveClient:
    """
    Manages direct authentication and Live Stream API interactions for a single creator model.
    """
    def __init__(self, creator_handle: str, username: str = "", password: str = "", totp_secret: str = ""):
        self.creator_handle = creator_handle.lstrip("@").lower()
        self.username = username or self.creator_handle
        self.password = password
        self.totp_secret = totp_secret
        self.session: Optional[AsyncSession] = None
        self.session_id: str = ""
        self.csrf_token: str = ""
        self.active_livestream_uuid: Optional[str] = None
        self.is_authenticated = False
        self.last_audience_mode = "public"
        self.is_loop_running: bool = False
        self.is_video_pause_active: bool = False
        self._last_login_timestamp: float = 0.0
        self._last_login_failed_at: float = 0.0

    async def _ensure_session(self):
        if not self.session:
            self.session = AsyncSession(impersonate="chrome124", timeout=15)

    def _get_cookies(self) -> Dict[str, str]:
        cookies = {}
        if self.session_id:
            cookies["sessionid"] = self.session_id
        if self.csrf_token:
            cookies["csrftoken"] = self.csrf_token
        return cookies

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://f2f.com",
            "referer": f"https://f2f.com/{self.creator_handle}/livestream",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        if self.csrf_token:
            headers["x-csrftoken"] = self.csrf_token
        return headers

    def _extract_cookies_from_response(self, resp):
        cookies = resp.cookies
        updated = []
        if "sessionid" in cookies:
            self.session_id = cookies["sessionid"]
            updated.append(f"sessionid={self.session_id[:8]}...")
        if "csrftoken" in cookies:
            self.csrf_token = cookies["csrftoken"]
            updated.append(f"csrftoken={self.csrf_token[:8]}...")
        if updated:
            logger.info(f"🍪 [@{self.creator_handle}] Extracted session cookies: {' | '.join(updated)}")

    async def login(self, max_attempts: int = 3) -> bool:
        """
        Battle-tested 4-step authentication method from ChatBridge.
        Supports both 2FA and Non-2FA accounts with autonomous retry.
        """
        if not self.password:
            logger.warning(f"⚠️ No password configured for @{self.creator_handle}. Running in simulated live mode.")
            self.is_authenticated = True
            return True

        await self._ensure_session()
        login_url = f"{BASE_URL}/auth/login/"
        last_rejected_otp = None

        for attempt in range(1, max_attempts + 1):
            try:
                # Step 1: Initialize CSRF session
                logger.info(f"🔑 [@{self.creator_handle}] Step 1/4: Initializing CSRF bootstrap session (Attempt {attempt}/{max_attempts})...")
                init_resp = await self.session.get("https://f2f.com/auth/login/", headers=self._get_headers())
                self._extract_cookies_from_response(init_resp)

                # Step 2: Generate UTC-safe TOTP code if configured
                otp_code = None
                if self.totp_secret:
                    try:
                        totp = pyotp.TOTP(self.totp_secret.replace(" ", "").upper())
                        now_utc_ts = int(time.time())
                        otp_code = totp.at(now_utc_ts)

                        # If this code was already rejected, wait for rotation
                        if otp_code == last_rejected_otp:
                            logger.info(f"⏳ [@{self.creator_handle}] Waiting for fresh TOTP window...")
                            for _ in range(35):
                                await asyncio.sleep(1)
                                fresh_code = totp.at(int(time.time()))
                                if fresh_code != last_rejected_otp:
                                    otp_code = fresh_code
                                    break

                        logger.info(f"🔑 [@{self.creator_handle}] Step 2/4: Generated fresh 2FA code ({otp_code}).")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to generate pyotp code: {e}")

                # Step 3: Submit login credentials
                payload = {
                    "email": self.username,
                    "username": self.username,
                    "password": self.password
                }
                if otp_code:
                    payload["otp_token"] = otp_code
                    payload["code"] = otp_code

                logger.info(f"🔑 [@{self.creator_handle}] Step 3/4: Submitting authentication payload to {login_url}...")
                resp = await self.session.post(login_url, json=payload, headers=self._get_headers(), cookies=self._get_cookies())
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

                # Step 3.5: Secondary 2FA check
                if resp.status_code in (200, 202) and (data.get("requires_2fa") or "verify_login" in str(data)):
                    logger.info(f"🔑 [@{self.creator_handle}] Step 3.5/4: Secondary 2FA verification required by F2F.")
                    self._extract_cookies_from_response(resp)

                    if not self.totp_secret:
                        logger.error(f"❌ TOTP secret missing for secondary 2FA verification on @{self.creator_handle}.")
                        return False

                    totp = pyotp.TOTP(self.totp_secret.replace(" ", "").upper())
                    otp_code = totp.at(int(time.time()))

                    verify_url = f"{BASE_URL}/auth/verify_login/"
                    verify_payload = {"code": otp_code}

                    verify_resp = await self.session.post(verify_url, json=verify_payload, headers=self._get_headers(), cookies=self._get_cookies())
                    if verify_resp.status_code == 200:
                        self._extract_cookies_from_response(verify_resp)
                        self._last_login_timestamp = time.time()
                        self.is_authenticated = True
                        logger.info(f"🎉 [@{self.creator_handle}] Step 4/4 Complete: Autonomous 2FA Login Successful!")
                        return True
                    else:
                        last_rejected_otp = otp_code
                        if attempt < max_attempts:
                            await asyncio.sleep(2)
                            continue
                        logger.error(f"❌ 2FA verification failed for @{self.creator_handle}: {verify_resp.text[:150]}")
                        return False

                elif resp.status_code == 200:
                    self._extract_cookies_from_response(resp)
                    self._last_login_timestamp = time.time()
                    self.is_authenticated = True
                    logger.info(f"🎉 [@{self.creator_handle}] Step 4/4 Complete: Autonomous Login Successful!")
                    return True
                else:
                    if "invalid-otp-token" in str(data).lower():
                        last_rejected_otp = otp_code
                        if attempt < max_attempts:
                            await asyncio.sleep(2)
                            continue
                    logger.error(f"❌ Login failed for @{self.creator_handle} (HTTP {resp.status_code}): {data}")
                    return False

            except Exception as e:
                logger.warning(f"⚠️ Exception during login attempt {attempt} for @{self.creator_handle}: {e}")
                if attempt < max_attempts:
                    await asyncio.sleep(2)
                    continue
                return False

        return False

    async def get_active_livestream(self) -> Optional[str]:
        """
        Discovers the current active livestream UUID for the creator model.
        """
        if not self.is_authenticated:
            await self.login()

        await self._ensure_session()
        endpoints = [
            f"{BASE_URL}/creators/{self.creator_handle}/livestream/",
            f"{BASE_URL}/creators/{self.creator_handle}/livestreams/active/",
            f"{BASE_URL}/livestreams/current/",
            f"{BASE_URL}/creators/{self.creator_handle}/livestream/chat/token"
        ]

        for url in endpoints:
            try:
                resp = await self.session.get(url, headers=self._get_headers(), cookies=self._get_cookies())
                if resp.status_code == 200:
                    data = resp.json()
                    uuid = data.get("uuid") or data.get("id") or data.get("livestream_uuid") or data.get("livestream_id")
                    if uuid:
                        self.active_livestream_uuid = str(uuid)
                        logger.info(f"📺 Discovered active livestream for @{self.creator_handle}: {self.active_livestream_uuid}")
                        return self.active_livestream_uuid
            except Exception as e:
                pass

        logger.info(f"ℹ️ Creator @{self.creator_handle} is not currently broadcasting live on F2F.")
        return None

    async def set_audience(self, target: str) -> bool:
        """
        Changes the livestream audience:
        - 'public': Global FYP Traffic (15s)
        - 'fans-and-followers': Subscribers & Followers Only (5s)
        """
        if not self.is_authenticated and self.password:
            await self.login()

        if not self.active_livestream_uuid:
            await self.get_active_livestream()

        if not self.active_livestream_uuid:
            logger.info(f"ℹ️ [FYP SWITCHER] Creator @{self.creator_handle} is not live on F2F. Skipping audience switch.")
            return False

        url = f"{BASE_URL}/livestreams/{self.active_livestream_uuid}/audience/"
        payload = {"target": target}

        logger.info(f"⚡ [FYP SWITCHER] Switching audience for @{self.creator_handle} to '{target.upper()}' (Livestream: {self.active_livestream_uuid})...")

        try:
            resp = await self.session.post(url, json=payload, headers=self._get_headers(), cookies=self._get_cookies())
            if resp.status_code in (200, 204):
                self.last_audience_mode = target
                logger.info(f"✅ Audience switched successfully for @{self.creator_handle} -> {target.upper()}")
                return True
            else:
                logger.warning(f"⚠️ Failed to switch audience ({resp.status_code}): {resp.text[:100]}")
        except Exception as e:
            logger.error(f"Error switching audience for @{self.creator_handle}: {e}")
        return False

    async def set_tip_goal(self, tip_goal: int) -> bool:
        """
        Updates the active livestream tip goal amount.
        """
        if not self.is_authenticated and self.password:
            await self.login()

        if not self.active_livestream_uuid:
            await self.get_active_livestream()

        if not self.active_livestream_uuid:
            logger.info(f"ℹ️ [TIP GOAL] Creator @{self.creator_handle} is not live on F2F. Skipping tip goal update.")
            return False

        url = f"{BASE_URL}/livestreams/{self.active_livestream_uuid}/tipgoal/"
        payload = {"tip_goal": tip_goal}

        try:
            resp = await self.session.post(url, json=payload, headers=self._get_headers(), cookies=self._get_cookies())
            if resp.status_code in (200, 201, 204):
                logger.info(f"✅ Tip goal updated for @{self.creator_handle} -> €{tip_goal}")
                return True
            else:
                logger.warning(f"⚠️ Failed to update tip goal ({resp.status_code}): {resp.text[:100]}")
        except Exception as e:
            logger.error(f"Error updating tip goal for @{self.creator_handle}: {e}")
        return False

    async def handle_video_ending_pause(self, delay_sec: float = 10.0):
        """
        Pauses or switches audience on video end, waits for loop delay, then resumes smoothly.
        Skips gracefully if the creator is not currently live on F2F.
        """
        if not self.active_livestream_uuid:
            await self.get_active_livestream()

        if not self.active_livestream_uuid:
            logger.info(f"ℹ️ [VIDEO END ACTION] Creator @{self.creator_handle} is not live on F2F right now. Skipping loop pause.")
            return

        self.is_video_pause_active = True
        logger.info(f"🚨 [VIDEO END ACTION] Handling loop end for @{self.creator_handle}. Holding FYP loop for {delay_sec}s while camera pauses...")

        # Hold for configured delay
        await asyncio.sleep(delay_sec)

        logger.info(f"▶️ [VIDEO END RESUME] Video loop restarted in OBS for @{self.creator_handle}!")
        self.is_video_pause_active = False

    async def start_fyp_loop(self, global_sec: int = 15, followers_sec: int = 5):
        """
        Runs the 15s Global (public) <-> 5s Followers (fans-and-followers) continuous FYP loop.
        """
        if self.is_loop_running:
            logger.info(f"🔄 FYP Switcher loop already running for @{self.creator_handle}")
            return

        self.is_loop_running = True
        logger.info(f"🔄 Starting Continuous FYP Switcher for @{self.creator_handle} ({global_sec}s Global ⟷ {followers_sec}s Followers)...")

        while self.is_loop_running:
            try:
                # Check if live
                live_uuid = await self.get_active_livestream()
                if not live_uuid:
                    logger.info(f"ℹ️ [@{self.creator_handle}] Not live on F2F. Checking again in 5s...")
                    await asyncio.sleep(5)
                    continue

                # Wait if a video-ending pause is currently in progress
                while self.is_video_pause_active and self.is_loop_running:
                    await asyncio.sleep(0.5)

                # Phase 1: Global FYP (15s)
                if not self.is_video_pause_active:
                    logger.info(f"🌐 [@{self.creator_handle}] FYP Phase: PUBLIC (Global Traffic) for {global_sec}s")
                    await self.set_audience("public")
                
                for _ in range(global_sec * 2):
                    if not self.is_loop_running:
                        break
                    if self.is_video_pause_active:
                        break
                    await asyncio.sleep(0.5)

                if not self.is_loop_running:
                    break

                # Wait if a video-ending pause triggered
                while self.is_video_pause_active and self.is_loop_running:
                    await asyncio.sleep(0.5)

                # Phase 2: Followers Only (5s)
                if not self.is_video_pause_active:
                    logger.info(f"👥 [@{self.creator_handle}] FYP Phase: FANS-AND-FOLLOWERS (Followers Only) for {followers_sec}s")
                    await self.set_audience("fans-and-followers")

                for _ in range(followers_sec * 2):
                    if not self.is_loop_running:
                        break
                    if self.is_video_pause_active:
                        break
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error in FYP switcher loop for @{self.creator_handle}: {e}")
                await asyncio.sleep(3)

    def stop_fyp_loop(self):
        self.is_loop_running = False
        logger.info(f"⏹️ Stopped FYP Switcher loop for @{self.creator_handle}")

class CreatorManager:
    """
    Multi-account registry managing all creator live clients concurrently.
    """
    def __init__(self):
        self.creators: Dict[str, F2FLiveClient] = {}

    def get_or_create_creator(self, handle: str) -> F2FLiveClient:
        h = handle.lstrip("@").lower()
        if h not in self.creators:
            # Read credentials from environment if available (e.g. F2F_EMAIL_XSOPHIEX)
            email = os.getenv(f"F2F_EMAIL_{h.upper()}", os.getenv(f"F2F_USERNAME_{h.upper()}", os.getenv("F2F_USERNAME", h)))
            pwd = os.getenv(f"F2F_PASSWORD_{h.upper()}", os.getenv("F2F_PASSWORD", ""))
            totp = os.getenv(f"F2F_TOTP_{h.upper()}", os.getenv("F2F_TOTP_SECRET", ""))
            self.creators[h] = F2FLiveClient(h, username=email, password=pwd, totp_secret=totp)
            logger.info(f"👤 Registered Creator Model client: @{h} (Login: {email})")
        return self.creators[h]

# Global Singleton Manager
creator_manager = CreatorManager()
