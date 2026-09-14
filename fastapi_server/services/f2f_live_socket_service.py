"""
Direct F2F Live Chat WebSocket Engine for FastAPI.
Connects directly to wss://socket.f2f.net/ using creator authenticated tokens and active channel names.
Bypasses the browser and userscript completely for zero-latency, 100% reliable Live Chat & Moderation.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, List, Optional
import aiohttp
from services.f2f_live_service import creator_manager

logger = logging.getLogger("FastAPI-LiveSocket")

class F2FLiveSocketClient:
    """
    Maintains a persistent, authenticated WebSocket connection to F2F Live Engine for a single model.
    """
    def __init__(self, creator_handle: str):
        self.creator_handle = creator_handle.lstrip("@").lower()
        self.ws_url = "wss://socket.f2f.net/socket.io/?EIO=4&transport=websocket"
        self.is_connected = False
        self.is_running = False
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.listen_task: Optional[asyncio.Task] = None
        self.ping_task: Optional[asyncio.Task] = None
        
        # Live Stream & Channel State
        self.active_channel_name: str = ""
        self.active_livestream_uuid: str = ""
        
        # Ephemeral Chat Queue (Sequence-based, auto-purged on stream end)
        self.incoming_chat_queue: List[Dict] = []
        self.chat_seq_counter: int = 0
        self.seen_message_ids: set = set()
        self.chat_token: str = ""
        self.has_joined_room: bool = False
        self.last_raw_packet: str = ""
        self.last_error: str = ""
        self.last_packet_time: float = 0

    async def get_live_details_and_token(self) -> tuple:
        """
        Fetches the active livestream channel_name and official JWT Live Chat Socket Token using creator session.
        """
        creator_client = creator_manager.get_or_create_creator(self.creator_handle)
        if not creator_client.is_authenticated:
            await creator_client.login()

        await creator_client._ensure_session()
        headers = creator_client._get_headers()
        cookies = creator_client._get_cookies()

        channel_name = ""
        token = ""

        # 1. Fetch Live Stream Details (channel_name, uuid)
        try:
            live_resp = await creator_client.session.get(
                f"https://f2f.com/api/creators/{self.creator_handle}/livestream/",
                headers=headers,
                cookies=cookies
            )
            if live_resp.status_code == 401:
                logger.warning(f"🔄 [@{self.creator_handle}] Session expired (401). Re-authenticating...")
                await creator_client.login()
                headers = creator_client._get_headers()
                cookies = creator_client._get_cookies()
                live_resp = await creator_client.session.get(
                    f"https://f2f.com/api/creators/{self.creator_handle}/livestream/",
                    headers=headers,
                    cookies=cookies
                )

            if live_resp.status_code == 200:
                live_data = live_resp.json()
                channel_name = live_data.get("channel_name") or live_data.get("channel") or ""
                self.active_livestream_uuid = live_data.get("uuid") or live_data.get("id") or ""
                if channel_name:
                    self.active_channel_name = channel_name
                    logger.info(f"📺 [@{self.creator_handle}] Discovered Live Channel: '{channel_name}' (UUID: {self.active_livestream_uuid})")
        except Exception as e:
            logger.debug(f"Live details fetch error for @{self.creator_handle}: {e}")

        # If livestream UUID was already discovered by creator_client (e.g. FYP loop), reuse it!
        if not self.active_livestream_uuid and creator_client.active_livestream_uuid:
            self.active_livestream_uuid = creator_client.active_livestream_uuid

        # Fallback channel name to creator handle so it is NEVER blank
        if not channel_name:
            channel_name = self.creator_handle
            self.active_channel_name = channel_name

        # 2. Fetch Official F2F Socket Token (Required for Socket.IO authentication)
        socket_url = "https://f2f.com/api/socket/token/"
        try:
            resp = await creator_client.session.get(socket_url, headers=headers, cookies=cookies)
            if resp.status_code == 401:
                await creator_client.login()
                headers = creator_client._get_headers()
                cookies = creator_client._get_cookies()
                resp = await creator_client.session.get(socket_url, headers=headers, cookies=cookies)

            if resp.status_code == 200:
                data = resp.json()
                t = data.get("token")
                if t:
                    token = t
                    logger.info(f"🔑 [@{self.creator_handle}] Retrieved Live Chat JWT Socket Token from socket/token!")
        except Exception as e:
            logger.debug(f"Token fetch exception for @{self.creator_handle}: {e}")

        # 3. Fetch Creator Room Chat Token (Required for livestream:chat:user:join)
        chat_token_url = f"https://f2f.com/api/creators/{self.creator_handle}/livestream/chat/token"
        try:
            resp_chat = await creator_client.session.get(chat_token_url, headers=headers, cookies=cookies)
            if resp_chat.status_code == 200:
                data_chat = resp_chat.json()
                self.chat_token = data_chat.get("token", "")
                ch = data_chat.get("channel_name") or data_chat.get("channel")
                if ch:
                    self.active_channel_name = str(ch)
                    channel_name = str(ch)
                if self.chat_token:
                    logger.info(f"🔑 [@{self.creator_handle}] Retrieved Creator Chat Room Token for room joining!")
        except Exception as e:
            logger.debug(f"Chat token fetch exception for @{self.creator_handle}: {e}")

        return channel_name, token

    async def start(self):
        """Starts the persistent background connection to F2F Live WebSocket."""
        if self.is_running:
            return
        self.is_running = True
        self.listen_task = asyncio.create_task(self._socket_lifecycle_loop())

    async def stop(self):
        """Stops the socket connection and cleanly purges ephemeral memory."""
        self.is_running = False
        self.is_connected = False
        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()
        if self.ping_task and not self.ping_task.done():
            self.ping_task.cancel()
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.session and not self.session.closed:
            await self.session.close()

        # Ephemeral memory purge
        self.incoming_chat_queue.clear()
        self.seen_message_ids.clear()
        logger.info(f"🛑 [@{self.creator_handle}] Disconnected from F2F WebSocket & Ephemeral Live Chat Memory Purged.")

    async def _socket_lifecycle_loop(self):
        """Autonomous auto-reconnect lifecycle loop for F2F Live WebSocket."""
        while self.is_running:
            try:
                creator_client = creator_manager.get_or_create_creator(self.creator_handle)
                if not creator_client.password:
                    logger.debug(f"ℹ️ [@{self.creator_handle}] Live socket idle: No credentials configured in .env.")
                    await asyncio.sleep(60)
                    continue

                channel_name, token = await self.get_live_details_and_token()
                if not token:
                    logger.info(f"ℹ️ [@{self.creator_handle}] Waiting for creator to be live on F2F to connect Live Chat...")
                    await asyncio.sleep(15)
                    continue

                cookie_str = "; ".join([f"{k}={v}" for k, v in creator_client._get_cookies().items()])
                headers = {
                    "Origin": "https://f2f.com",
                    "Referer": f"https://f2f.com/{self.creator_handle}/livestream",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
                    "Accept-Language": "en-IN,en;q=0.9,bn-IN;q=0.8,bn;q=0.7,en-GB;q=0.6,en-US;q=0.5",
                    "Sec-Ch-Ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"macOS"',
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    "Cookie": cookie_str
                }

                if not self.session or self.session.closed:
                    self.session = aiohttp.ClientSession()

                logger.info(f"⚡ [@{self.creator_handle}] Connecting directly to F2F Live WebSocket: {self.ws_url} (Channel: '{self.active_channel_name}')...")
                # Removed heartbeat=20.0 to prevent aiohttp ping conflict with Socket.IO Engine.io keepalive
                async with self.session.ws_connect(self.ws_url, headers=headers) as ws:
                    self.ws = ws
                    
                    # 1. Wait for engine.io open packet ("0{...}")
                    handshake_msg = await ws.receive_str()
                    logger.info(f"🤝 [@{self.creator_handle}] Engine.io handshake received: {handshake_msg[:60]}...")
                    
                    # 2. Send Socket.IO v4 auth connect packet ("40{"token":"..."}")
                    connect_packet = "40" + json.dumps({"token": token})
                    await ws.send_str(connect_packet)
                    
                    # 3. Receive auth confirmation
                    auth_confirm = await ws.receive_str()
                    if not auth_confirm.startswith("40"):
                        logger.error(f"❌ [@{self.creator_handle}] WebSocket Auth rejected by F2F server: {auth_confirm}")
                        self.is_connected = False
                        await asyncio.sleep(5)
                        continue

                    logger.info(f"🎉 [@{self.creator_handle}] Live Chat WebSocket AUTHENTICATED! (sid: {auth_confirm[:30]})")
                    self.is_connected = True

                    # 4. Join the Creator's Live Chat Room via official F2F "livestream:chat:user:join" packet!
                    target_channel = self.active_channel_name or self.creator_handle
                    join_packet = "42" + json.dumps(["livestream:chat:user:join", target_channel, self.chat_token or ""])
                    await ws.send_str(join_packet)
                    self.has_joined_room = True
                    self.joined_channel_name = target_channel
                    logger.info(f"🚪 [@{self.creator_handle}] Dispatched 'livestream:chat:user:join' to room '{target_channel}'!")

                    # 5. Launch background stream monitor task to auto-join if creator goes live mid-session
                    monitor_task = asyncio.create_task(self._stream_monitor_loop(ws))

                    try:
                        # 6. Process incoming socket frames
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_incoming_packet(msg.data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                logger.warning(f"⚠️ [@{self.creator_handle}] Socket closed or error: {msg}")
                                break
                    finally:
                        monitor_task.cancel()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"⚠️ [@{self.creator_handle}] F2F WebSocket connection error: {e}. Reconnecting in 5s...")
            
            self.is_connected = False
            if self.is_running:
                await asyncio.sleep(5)

    async def _stream_monitor_loop(self, ws):
        """Continuously checks if creator switches channel, starts a new stream, or if session expires."""
        while not ws.closed and self.is_connected:
            try:
                await asyncio.sleep(4)
                creator_client = creator_manager.get_or_create_creator(self.creator_handle)
                headers = creator_client._get_headers()
                cookies = creator_client._get_cookies()
                live_resp = await creator_client.session.get(
                    f"https://f2f.com/api/creators/{self.creator_handle}/livestream/",
                    headers=headers,
                    cookies=cookies
                )
                if live_resp.status_code == 401:
                    logger.warning(f"🔄 [@{self.creator_handle}] Session expired (401). Re-authenticating...")
                    await creator_client.login()
                    continue

                if live_resp.status_code in (404, 204, 400):
                    # Stream is offline or ended
                    if getattr(self, "has_joined_room", False):
                        logger.info(f"ℹ️ [@{self.creator_handle}] Livestream offline / ended (HTTP {live_resp.status_code}). Resetting room state for next stream...")
                        self.has_joined_room = False
                        self.joined_channel_name = ""
                        self.active_livestream_uuid = ""
                    continue

                if live_resp.status_code == 200:
                    live_data = live_resp.json()
                    new_channel = live_data.get("channel_name") or live_data.get("channel") or ""
                    new_uuid = str(live_data.get("uuid") or live_data.get("id") or "")

                    if not new_channel:
                        if getattr(self, "has_joined_room", False):
                            self.has_joined_room = False
                            self.joined_channel_name = ""
                        continue

                    # Check if brand new stream, new channel, or room needs joining
                    is_new_stream = (
                        (new_channel != getattr(self, "joined_channel_name", "")) or
                        (new_uuid and new_uuid != self.active_livestream_uuid) or
                        not getattr(self, "has_joined_room", False)
                    )

                    if is_new_stream:
                        logger.info(f"📺 [@{self.creator_handle}] New / restarted livestream active! (Channel: '{new_channel}', UUID: '{new_uuid}'). Auto-joining room...")
                        self.active_channel_name = new_channel
                        self.active_livestream_uuid = new_uuid

                        # Fetch fresh chat token
                        chat_token_url = f"https://f2f.com/api/creators/{self.creator_handle}/livestream/chat/token"
                        try:
                            resp_chat = await creator_client.session.get(chat_token_url, headers=headers, cookies=cookies)
                            if resp_chat.status_code == 200:
                                self.chat_token = resp_chat.json().get("token", "")
                        except Exception:
                            pass

                        join_packet = "42" + json.dumps(["livestream:chat:user:join", self.active_channel_name, self.chat_token or ""])
                        await ws.send_str(join_packet)
                        self.has_joined_room = True
                        self.joined_channel_name = self.active_channel_name
                        logger.info(f"🚪 [@{self.creator_handle}] Successfully joined live room: '{self.active_channel_name}'!")
            except Exception as e:
                logger.debug(f"Stream monitor tick error: {e}")

    async def _handle_incoming_packet(self, data: str):
        """Parses Engine.io / Socket.io packets from F2F Live with bulletproof regex/json index search."""
        self.last_raw_packet = data[:300]
        self.last_packet_time = time.time()
        try:
            # 1. Keepalive ping/pong
            if data.startswith("2"):
                if self.ws and not self.ws.closed:
                    await self.ws.send_str("3")
                return

            # 2. Socket.IO Event Packet: Starts with '42' (with optional ack ID, e.g. '42', '420', '421')
            if data.startswith("42"):
                json_start = data.find("[")
                if json_start == -1:
                    return

                parsed = json.loads(data[json_start:])
                if not isinstance(parsed, list) or len(parsed) == 0:
                    return

                event_name = parsed[0]
                payload = parsed[1] if len(parsed) > 1 else None

                logger.info(f"🔔 [@{self.creator_handle}] Socket Event Received: '{event_name}'")

                # Extract dictionary item whether payload is list or dict
                item = payload if isinstance(payload, dict) else {}
                if isinstance(payload, list):
                    for el in payload:
                        if isinstance(el, dict):
                            item = el
                            break

                # Case A: Chat Message Event (Exclude system join/leave events)
                if ("message" in event_name or "chat" in event_name) and "delete" not in event_name and "joined" not in event_name and "left" not in event_name and item:
                    msg_id = item.get("id") or str(uuid.uuid4())[:8]
                    content = (item.get("content") or item.get("message") or item.get("text") or "").strip()
                    if not content or "joined" in content.lower() or item.get("type") in ("joined", "system"):
                        return

                    user_obj = item.get("user") or {}
                    username = (
                        (user_obj.get("display_name") if isinstance(user_obj, dict) else None) or 
                        (user_obj.get("name") if isinstance(user_obj, dict) else None) or 
                        (user_obj.get("nickname") if isinstance(user_obj, dict) else None) or 
                        item.get("display_name") or 
                        item.get("name") or 
                        (user_obj.get("username") if isinstance(user_obj, dict) else None) or 
                        item.get("username") or 
                        "Fan"
                    )
                    tip_amount = item.get("amount") or item.get("tip_amount") or 0
                    is_tip = tip_amount > 0 or (item.get("type") == "tip") or ("€" in content)

                    if "#" in str(msg_id):
                        ch = str(msg_id).split("#")[0]
                        if ch and not self.active_channel_name:
                            self.active_channel_name = ch

                    msg_hash = str(msg_id) if msg_id else f"{username}:{content}"
                    if msg_hash not in self.seen_message_ids:
                        self.seen_message_ids.add(msg_hash)
                        self.chat_seq_counter += 1
                        
                        chat_item = {
                            "seq_id": self.chat_seq_counter,
                            "id": msg_id,
                            "creator": self.creator_handle,
                            "username": username,
                            "text": content,
                            "type": "tip" if is_tip else "chat",
                            "tip_amount": tip_amount,
                            "timestamp": time.time()
                        }
                        self.incoming_chat_queue.append(chat_item)
                        if len(self.incoming_chat_queue) > 100:
                            self.incoming_chat_queue.pop(0)

                        logger.info(f"📥 [@{self.creator_handle}] [DIRECT WS CHAT] [Seq #{self.chat_seq_counter}] {username}: {content}")

                # Case B: Tip Received Event
                elif "tip" in event_name and item:
                    u_dict = item.get("user") or {}
                    tip_user = (
                        (u_dict.get("display_name") if isinstance(u_dict, dict) else None) or
                        (u_dict.get("name") if isinstance(u_dict, dict) else None) or
                        item.get("display_name") or 
                        item.get("name") or 
                        item.get("username") or 
                        (u_dict.get("username") if isinstance(u_dict, dict) else None) or 
                        "Fan"
                    )
                    tip_amt = item.get("amount") or item.get("total_tip_revenue") or 0
                    self.chat_seq_counter += 1
                    
                    chat_item = {
                        "seq_id": self.chat_seq_counter,
                        "id": item.get("id") or str(uuid.uuid4())[:8],
                        "creator": self.creator_handle,
                        "username": tip_user,
                        "text": f"€{tip_amt}",
                        "type": "tip",
                        "tip_amount": tip_amt,
                        "timestamp": time.time()
                    }
                    self.incoming_chat_queue.append(chat_item)
                    logger.info(f"💸 [@{self.creator_handle}] [DIRECT WS TIP] {tip_user}: €{tip_amt}")

        except Exception as e:
            logger.error(f"⚠️ Error parsing incoming packet '{data[:100]}': {e}")

    async def send_chat(self, text: str) -> bool:
        """Sends a live chat message directly into the F2F Live Stream over WebSocket."""
        if not self.ws or self.ws.closed or not self.is_connected:
            logger.warning(f"⚠️ [@{self.creator_handle}] Cannot send chat: WebSocket is not connected.")
            return False

        channel = self.active_channel_name or self.creator_handle
        payload = ["livestream:chat:message:send", channel, text]
        packet = "42" + json.dumps(payload)
        
        try:
            await self.ws.send_str(packet)
            logger.info(f"💬 [@{self.creator_handle}] [DIRECT WS DISPATCH] Sent live chat: '{text}' to channel '{channel}'")
            return True
        except Exception as e:
            logger.error(f"❌ Error sending live chat over WebSocket: {e}")
            return False

    async def delete_chat(self, message_id: str) -> bool:
        """Deletes a message from the F2F Live Stream directly over WebSocket."""
        if not self.ws or self.ws.closed or not self.is_connected:
            logger.warning(f"⚠️ [@{self.creator_handle}] Cannot delete chat: WebSocket is not connected.")
            return False

        channel = self.active_channel_name or self.creator_handle
        payload = ["livestream:chat:message:delete", channel, str(message_id)]
        packet = "42" + json.dumps(payload)

        try:
            await self.ws.send_str(packet)
            logger.info(f"🗑️ [@{self.creator_handle}] [DIRECT WS DELETE] Dispatched delete for message ID: {message_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error deleting live chat over WebSocket: {e}")
            return False

    def find_message_id(self, text: str = "", username: str = "") -> Optional[str]:
        """Finds matching message ID in recent chat queue by text and/or username."""
        text_clean = text.strip().lower()
        user_clean = username.strip().lower()
        for item in reversed(self.incoming_chat_queue):
            item_text = (item.get("text") or "").strip().lower()
            item_user = (item.get("username") or "").strip().lower()
            if text_clean and item_text and (text_clean == item_text or text_clean in item_text):
                return str(item.get("id"))
            if user_clean and item_user and user_clean == item_user:
                return str(item.get("id"))
        return None

    def get_incoming_chats(self, since_seq: int = 0) -> List[Dict]:
        """Returns new live chats since sequence ID."""
        if since_seq > 0:
            return [c for c in self.incoming_chat_queue if c.get("seq_id", 0) > since_seq]
        return list(self.incoming_chat_queue)


class F2FLiveChatManager:
    """Manages Live WebSocket instances across all creator models."""
    def __init__(self):
        self.clients: Dict[str, F2FLiveSocketClient] = {}

    def get_client(self, creator_handle: str) -> F2FLiveSocketClient:
        clean = creator_handle.lstrip("@").lower()
        if clean not in self.clients:
            self.clients[clean] = F2FLiveSocketClient(clean)
        return self.clients[clean]

    async def start_all(self):
        """Starts socket listeners only for configured active models."""
        for handle in ["xsophiex", "chantalkuyt", "aylen", "zoelynn"]:
            creator_client = creator_manager.get_or_create_creator(handle)
            if creator_client.password:
                client = self.get_client(handle)
                await client.start()

live_chat_manager = F2FLiveChatManager()
