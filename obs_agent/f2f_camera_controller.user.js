// ==UserScript==
// @name         F2F Live OBS Camera & Chat Automation
// @namespace    http://tampermonkey.net/
// @version      3.5
// @description  Full F2F Live Stream Automation: Instant Double-Event Camera Toggle Engine (Camera ON/OFF), Precision Live Chat Scraper, Bulletproof End Stream, Direct WebSocket Relay, Multi-Strategy Input Finder, React Value Tracker Reset, Auto Port Discovery, Go Live
// @match        https://f2f.com/*
// @match        https://*.f2f.com/*
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @grant        window.close
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-start
// ==/UserScript==

(function () {
    'use strict';

    const pageWindow = unsafeWindow;
    const pageDoc = pageWindow.document;

    console.log("%c[F2F-OBS] v3.6 Pure WebSocket Chat & Camera Controller Active", "color: #10b981; font-weight: bold; font-size: 16px;");

    // ─── Creator Profiles & Authoritative Port/Camera Matrix ─────
    const CREATORS = {
        "xsophiex": {
            name: "Sophie",
            handle: "@xsophiex",
            port: 8081,
            obsPort: 4455,
            defaultCamera: "OBS Cam 0",
            cameraKeywords: ["obs cam 0", "video0", "obs virtual camera 0", "obs virtual camera (0)"]
        },
        "chantalkuyt": {
            name: "Chantal",
            handle: "@chantalkuyt",
            port: 8082,
            obsPort: 4456,
            defaultCamera: "OBS Cam 2",
            cameraKeywords: ["obs cam 2", "video2", "obs virtual camera 2", "obs virtual camera (2)"]
        },
        "aylen": {
            name: "Aylen",
            handle: "@aylen",
            port: 8083,
            obsPort: 4457,
            defaultCamera: "OBS Cam 3",
            cameraKeywords: ["obs cam 3", "video3", "obs virtual camera 3", "obs virtual camera (3)"]
        },
        "zoelynn": {
            name: "Zoe Lynn",
            handle: "@zoelynn",
            port: 8084,
            obsPort: 4458,
            defaultCamera: "OBS Cam 1",
            cameraKeywords: ["obs cam 1", "video1", "obs virtual camera 1", "obs virtual camera (1)"]
        }
    };

    // ─── Multi-Tier Creator Identity Resolution ───────────────────
    function resolveActiveCreator() {
        // Tier 1: URL Query (?creator=... or ?model=...)
        try {
            var urlParams = new URLSearchParams(pageWindow.location.search);
            var fromQuery = urlParams.get("creator") || urlParams.get("model");
            if (fromQuery && CREATORS[fromQuery.toLowerCase()]) {
                var q = fromQuery.toLowerCase();
                localStorage.setItem("f2f_active_creator", q);
                return q;
            }
        } catch (e) { }

        // Tier 2: URL Hash (#creator=... or #model=...)
        try {
            if (pageWindow.location.hash) {
                var hashParams = new URLSearchParams(pageWindow.location.hash.replace(/^#/, ""));
                var fromHash = hashParams.get("creator") || hashParams.get("model");
                if (fromHash && CREATORS[fromHash.toLowerCase()]) {
                    var h = fromHash.toLowerCase();
                    localStorage.setItem("f2f_active_creator", h);
                    return h;
                }
            }
        } catch (e) { }

        // Tier 3: Saved in this Chrome Profile's isolated localStorage
        try {
            var saved = localStorage.getItem("f2f_active_creator");
            if (saved && CREATORS[saved.toLowerCase()]) {
                return saved.toLowerCase();
            }
        } catch (e) { }

        // Tier 4: DOM Auto-detect (from pathname, title, or body text)
        try {
            var path = pageWindow.location.pathname.toLowerCase();
            for (var key in CREATORS) {
                if (path.includes(key)) {
                    localStorage.setItem("f2f_active_creator", key);
                    return key;
                }
            }
        } catch (e) { }

        return "xsophiex";
    }

    var activeCreator = resolveActiveCreator();
    var creatorCfg = CREATORS[activeCreator] || CREATORS["xsophiex"];
    var agentPort = creatorCfg.port;
    var targetCameraName = localStorage.getItem("f2f_target_camera_" + activeCreator) || creatorCfg.defaultCamera;
    var isConnected = false;
    var lastProcessedEventId = 0;
    var detectedVideoDevices = [];

    console.log("%c[F2F-OBS] 🎯 Active Creator: " + creatorCfg.name + " | Port: " + agentPort + " | Target Camera: " + targetCameraName, "color: #10b981; font-weight: bold; font-size: 14px;");

    // ─── Enumerate Devices Helper ─────────────────────────────────
    var origEnumerateDevices = (pageWindow.navigator && pageWindow.navigator.mediaDevices && pageWindow.navigator.mediaDevices.enumerateDevices)
        ? pageWindow.navigator.mediaDevices.enumerateDevices.bind(pageWindow.navigator.mediaDevices)
        : async function () { return []; };

    // ─── Hook getUserMedia: Direct Clean OBS Camera Stream ─────────
    if (pageWindow.navigator && pageWindow.navigator.mediaDevices && pageWindow.navigator.mediaDevices.getUserMedia) {
        var origGetUserMedia = pageWindow.navigator.mediaDevices.getUserMedia.bind(pageWindow.navigator.mediaDevices);
        pageWindow.navigator.mediaDevices.getUserMedia = async function (constraints) {
            try {
                if (constraints && constraints.video) {

                    var rawDevs = await origEnumerateDevices();
                    var videoDevs = rawDevs.filter(function (d) { return d.kind === "videoinput"; });
                    detectedVideoDevices = videoDevs;

                    var targetDev = videoDevs.find(function (d) {
                        if (!d.label) return false;
                        var lbl = d.label.toLowerCase();
                        if (targetCameraName && lbl.includes(targetCameraName.toLowerCase())) return true;
                        if (creatorCfg && creatorCfg.cameraKeywords) {
                            return creatorCfg.cameraKeywords.some(function (kw) { return lbl.includes(kw); });
                        }
                        return lbl.includes("obs") || lbl.includes("virtual");
                    });

                    if (targetDev && targetDev.deviceId) {
                        console.log("%c[F2F-OBS] 🔒 Connecting Real OBS Camera: " + targetDev.label + " (" + targetDev.deviceId + ")", "color: #10b981; font-weight: bold;");
                        if (typeof constraints.video === "boolean") {
                            constraints.video = { deviceId: { exact: targetDev.deviceId } };
                        } else if (typeof constraints.video === "object") {
                            constraints.video.deviceId = { exact: targetDev.deviceId };
                        }
                    } else {
                        console.log("%c[F2F-OBS] 🎥 OBS Camera device note: passing through to system video stream", "color: #3b82f6; font-weight: bold;");
                    }
                    return origGetUserMedia(constraints);
                }
            } catch (err) {
                console.warn("[F2F-OBS] getUserMedia hook exception:", err);
            }
            return origGetUserMedia(constraints);
        };
    }

    var liveSocket = null;
    var activeChannelName = "";
    var activeChatToken = "";
    var seenMessageIds = new Set();
    var lastWsMessageTime = 0;

    // ─── Pure WebSocket Chat Interceptor (No DOM Scraping) ────────
    function attachLiveChatListener(ws) {
        if (!ws || ws.__f2f_chat_attached) return;
        ws.__f2f_chat_attached = true;
        liveSocket = ws;
        lastWsMessageTime = Date.now();
        console.log("%c[F2F-OBS] ⚡ Hooked F2F Live WebSocket Successfully!", "color: #3b82f6; font-weight: bold; font-size: 14px;");

        // Track WebSocket close/error to invalidate stale references
        ws.addEventListener("close", function () {
            console.log("[F2F-OBS] ⚠️ F2F WebSocket closed. DOM scanner will take over.");
            if (liveSocket === ws) liveSocket = null;
        });
        ws.addEventListener("error", function () {
            if (liveSocket === ws) liveSocket = null;
        });

        // Hook ws.send to capture activeChannelName and token from livestream:chat:user:join packets
        try {
            var origSend = ws.send.bind(ws);
            ws.send = function (data) {
                try {
                    if (typeof data === "string" && data.startsWith("42")) {
                        var jsonStart = data.indexOf("[");
                        if (jsonStart !== -1) {
                            var p = JSON.parse(data.substring(jsonStart));
                            if (p[0] === "livestream:chat:user:join" && p[1]) {
                                activeChannelName = String(p[1]);
                                if (p[2]) activeChatToken = String(p[2]);
                                console.log("%c[F2F-OBS] 🚪 Captured Active Livestream Channel: " + activeChannelName, "color: #10b981; font-weight: bold;");
                            }
                        }
                    }
                } catch (e) { }
                return origSend(data);
            };
        } catch (e) { }

        ws.addEventListener("message", function (event) {
            try {
                var data = event.data;
                if (typeof data !== "string") return;

                if (ws.readyState === 1) liveSocket = ws;
                lastWsMessageTime = Date.now();

                if (data.startsWith("2")) return; // Engine.IO ping

                if (data.startsWith("42")) {
                    var jsonStart = data.indexOf("[");
                    if (jsonStart === -1) return;
                    var parsed = JSON.parse(data.substring(jsonStart));
                    var eventName = parsed[0];
                    var payload = parsed[1];

                    // 1. Live Chat Comment Sent
                    if (eventName === "livestream:chat:message:sent" && payload) {
                        var msgId = payload.id || "";
                        var content = (payload.content || payload.message || "").trim();
                        var userObj = payload.user || {};
                        var username = (
                            userObj.display_name ||
                            userObj.name ||
                            userObj.nickname ||
                            payload.display_name ||
                            payload.name ||
                            userObj.username ||
                            payload.username ||
                            "Fan"
                        ).trim();

                        // If username is still a generic auto-generated ID (user-xxxx), inspect active DOM chat bubbles
                        if (username.startsWith("user-") && content) {
                            try {
                                var chatItems = Array.from(pageDoc.querySelectorAll("div[class*='chatMessage'], div[class*='messageItem'], div[class*='ChatMessage'], div[class*='comment']"));
                                for (var i = chatItems.length - 1; i >= 0; i--) {
                                    var it = chatItems[i];
                                    var itText = it.innerText || it.textContent || "";
                                    if (itText.includes(content)) {
                                        var authorEl = it.querySelector("span[class*='author'], div[class*='author'], span[class*='user'], div[class*='user'], span[class*='name'], div[class*='name'], strong, b");
                                        if (authorEl) {
                                            var domName = (authorEl.innerText || authorEl.textContent || "").trim();
                                            if (domName && !domName.startsWith("user-") && domName !== content) {
                                                username = domName;
                                                break;
                                            }
                                        }
                                    }
                                }
                            } catch (e) { }
                        }
                        var tipAmount = payload.amount || 0;
                        var isTip = tipAmount > 0 || (payload.type === "tip");

                        // 🛑 Filter creator's own messages so they never echo back to Discord
                        var handleClean = (activeCreator || "").toLowerCase().replace(/[@\s]/g, "");
                        var uLower = username.toLowerCase().replace(/[@\s]/g, "");
                        if (uLower.includes(handleClean) || handleClean.includes(uLower) || uLower.includes("sophie") || uLower.includes("chantal") || uLower.includes("zoe") || uLower.includes("aylen")) {
                            console.log("[F2F-OBS] 🛡️ Suppressed creator self-message from WebSocket relay:", username, content);
                            return;
                        }

                        if (msgId.includes("#")) {
                            activeChannelName = msgId.split("#")[0];
                        }

                        var msgHash = msgId || (username + ":" + content);
                        lastWsMessageTime = Date.now();
                        if (!seenMessageIds.has(msgHash)) {
                            seenMessageIds.add(msgHash);
                            if (msgId) seenMessageIds.add(msgId);
                            seenMessageIds.add(username.toLowerCase() + ":" + content.toLowerCase());
                            console.log("%c[F2F-OBS] 📥 [PURE WS CHAT] " + username + ": " + content, "color: #10b981; font-weight: bold; font-size: 14px;");

                            GM_xmlhttpRequest({
                                method: "POST",
                                url: "http://127.0.0.1:" + agentPort + "/api/incoming-chat",
                                headers: { "Content-Type": "application/json" },
                                data: JSON.stringify({
                                    id: msgId,
                                    username: username,
                                    text: content,
                                    type: isTip ? "tip" : "chat",
                                    tip_amount: tipAmount
                                })
                            });
                        }
                    }
                    // 2. Live Stream Tip Received
                    else if (eventName === "livestream:chat:tip:received" && payload) {
                        var tipUser = (
                            payload.display_name ||
                            payload.name ||
                            payload.nickname ||
                            (payload.user && (payload.user.display_name || payload.user.name || payload.user.nickname)) ||
                            payload.username ||
                            (payload.user && payload.user.username) ||
                            "Fan"
                        ).trim();
                        var tipAmt = payload.amount || payload.total_tip_revenue || 0;
                        console.log("%c[F2F-OBS] 💸 [PURE WS TIP] " + tipUser + ": €" + tipAmt, "color: #f59e0b; font-weight: bold; font-size: 14px;");
                        GM_xmlhttpRequest({
                            method: "POST",
                            url: "http://127.0.0.1:" + agentPort + "/api/incoming-chat",
                            headers: { "Content-Type": "application/json" },
                            data: JSON.stringify({
                                id: payload.id || "",
                                username: tipUser,
                                text: "€" + tipAmt,
                                type: "tip",
                                tip_amount: tipAmt
                            })
                        });
                    }
                }
            } catch (e) { }
        });

        // Maintain active liveSocket reference (DO NOT re-send join packet periodically, to prevent "creator joined" spam)
        var wsHeartbeatInterval = setInterval(function () {
            if (ws.readyState > 1) {
                clearInterval(wsHeartbeatInterval);
                if (liveSocket === ws) liveSocket = null;
                return;
            }
            if (ws.readyState === 1) {
                liveSocket = ws;
            }
        }, 15000);
    }

    try {
        if (pageWindow.WebSocket && !pageWindow.__f2f_ws_hooked) {
            pageWindow.__f2f_ws_hooked = true;
            pageWindow.WebSocket = new Proxy(pageWindow.WebSocket, {
                construct(target, args) {
                    var ws = Reflect.construct(target, args);
                    try {
                        var url = args[0];
                        if (typeof url === "string" && (url.includes("socket.f2f.net") || url.includes("f2f.com") || url.includes("socket.io"))) {
                            attachLiveChatListener(ws);
                        }
                    } catch (e) { }
                    return ws;
                }
            });
        }
    } catch (e) { }

    // ─── Chat Feed Auto-Scroll & Unfreeze Engine (Clears (↓) Button) ──
    var lastScrollCheckTime = 0;
    function ensureChatScrolledToBottom() {
        if (!pageDoc || !pageDoc.body) return;
        var now = Date.now();
        if (now - lastScrollCheckTime < 1200) return;
        lastScrollCheckTime = now;

        try {
            // 1. Detect and click the floating auto-scroll pause / new-messages / (↓) button
            var candidateBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
            for (var b of candidateBtns) {
                if (b.offsetWidth === 0 || b.offsetHeight === 0 || b.offsetHeight > 80) continue;
                if (b.id && (b.id.includes("f2f-") || b.id.includes("badge"))) continue;
                if (b.closest && (b.closest("#f2f-badge-container") || b.closest("#f2f-control-dock"))) continue;

                var cls = (b.className && typeof b.className === "string") ? b.className.toLowerCase() : "";
                var aria = (b.getAttribute("aria-label") || "").toLowerCase();
                var text = (b.innerText || b.textContent || "").trim().toLowerCase();
                var hasArrowSvg = false;
                var svg = b.querySelector("svg");
                if (svg) {
                    var svgHtml = svg.outerHTML.toLowerCase();
                    if (svgHtml.includes("arrow") || svgHtml.includes("chevron") || svgHtml.includes("down")) {
                        hasArrowSvg = true;
                    }
                }

                if (
                    cls.includes("scroll") || cls.includes("bottom") || cls.includes("down") || cls.includes("newmessage") ||
                    aria.includes("scroll") || aria.includes("bottom") || aria.includes("down") ||
                    text.includes("new message") || text.includes("nieuwe") || text.includes("↓") ||
                    hasArrowSvg
                ) {
                    try {
                        clickElementViaReact(b);
                        b.click();
                    } catch (e) { }
                    break;
                }
            }

            // 2. Programmatically scroll all chat containers to bottom
            var chatContainers = Array.from(pageDoc.querySelectorAll(
                "div[class*='chatList'], div[class*='ChatList'], div[class*='chatContainer'], div[class*='messages'], div[class*='Messages'], div[class*='chat-messages'], div[class*='Tc9FFW'], ul[class*='chat']"
            ));
            for (var c of chatContainers) {
                if (c.scrollHeight > c.clientHeight) {
                    c.scrollTop = c.scrollHeight;
                }
            }
        } catch (e) { }
    }

    // ─── Continuous Live Chat DOM Scanner (Sub-Second Zero-Latency Engine) ────
    function scanLiveChatDOM() {
        if (!pageDoc || !pageDoc.body) return;
        // If WebSocket is actively connected and healthy, rely 100% on pure WebSocket to avoid duplicates!
        if (liveSocket && liveSocket.readyState === 1 && (Date.now() - lastWsMessageTime < 45000)) {
            return;
        }
        try {
            var chatElements = Array.from(pageDoc.querySelectorAll(
                "div[class*='Tc9FFW_message'], div[class*='message'], div[class*='chatMessage'], div[class*='messageItem'], " +
                "div[class*='ChatMessage'], div[class*='MessageItem'], div[class*='comment'], div[class*='Comment'], " +
                "div[class*='livestreamChat'], li[class*='message'], div[class*='chat-message']"
            ));

            if (chatElements.length === 0) {
                var container = pageDoc.querySelector("div[class*='chatList'], div[class*='ChatList'], div[class*='chatContainer'], div[class*='messages']");
                if (container && container.children.length > 1) {
                    chatElements = Array.from(container.children);
                }
            }

            for (var el of chatElements) {
                var rawText = (el.innerText || el.textContent || "").trim();
                // Reject containers or multi-line blobs (> 150 chars or > 3 lines or with 'joined' / 'Tipmenu')
                if (!rawText || rawText.length < 2 || rawText.length > 150) continue;
                if (rawText.includes("\nNew messages") || rawText.includes("Tipmenu") || rawText.endsWith("joined") || rawText === "Chat" || rawText === "Follower" || rawText === "Subscriber") continue;

                var authorEl = el.querySelector("span[class*='author'], div[class*='author'], span[class*='user'], div[class*='user'], span[class*='name'], div[class*='name'], strong, b");
                var username = "";
                var messageText = "";

                if (authorEl) {
                    var authorClone = authorEl.cloneNode(true);
                    var badges = authorClone.querySelectorAll("span, div, svg, img, i, em, small");
                    badges.forEach(function (b) {
                        var txt = (b.innerText || "").toLowerCase();
                        if (/follower|subscriber|sub|vip|mod|badge/i.test(b.className || "") || /follower|subscriber|vip|mod/i.test(txt)) {
                            b.remove();
                        }
                    });
                    username = (authorClone.innerText || authorClone.textContent || "").trim();
                    username = username.split(/[\n\r]/)[0].replace(/\b(Follower|Subscriber|VIP|Moderator)\b/gi, "").trim();
                    messageText = rawText.replace(username, "").replace(/^[:\s\-]+/, "").trim();
                } else {
                    var lines = rawText.split("\n").map(function (l) { return l.trim(); }).filter(function (l) { return l.length > 0; });
                    if (lines.length === 2 && lines[0].length < 35) {
                        username = lines[0].replace(/\b(Follower|Subscriber|VIP|Moderator)\b/gi, "").trim();
                        messageText = lines[1].trim();
                    } else if (rawText.includes(":") && !rawText.startsWith("http")) {
                        var parts = rawText.split(":");
                        username = parts[0].replace(/\b(Follower|Subscriber|VIP|Moderator)\b/gi, "").trim();
                        messageText = parts.slice(1).join(":").trim();
                    }
                }

                if (username && messageText && username.length < 40 && messageText.length > 0 && !messageText.endsWith("joined") && messageText !== username) {
                    var handleClean = (activeCreator || "").toLowerCase().replace(/[@\s]/g, "");
                    if (username.toLowerCase().replace(/[@\s]/g, "").includes(handleClean)) continue;

                    var hash = username.toLowerCase() + ":" + messageText.toLowerCase();
                    if (!seenMessageIds.has(hash) && !seenMessageIds.has(username + ":" + messageText)) {
                        seenMessageIds.add(hash);
                        seenMessageIds.add(username + ":" + messageText);
                        console.log("%c[F2F-OBS] 💬 [DOM CHAT CAPTURED] " + username + ": " + messageText, "color: #10b981; font-weight: bold; font-size: 14px;");

                        var isTip = messageText.includes("€");
                        var tipAmount = 0;
                        if (isTip) {
                            var tipMatch = messageText.match(/€\s*(\d+(?:[.,]\d+)?)/);
                            if (tipMatch) tipAmount = parseFloat(tipMatch[1].replace(",", "."));
                        }

                        GM_xmlhttpRequest({
                            method: "POST",
                            url: "http://127.0.0.1:" + agentPort + "/api/incoming-chat",
                            headers: { "Content-Type": "application/json" },
                            data: JSON.stringify({
                                id: hash,
                                username: username,
                                text: messageText,
                                type: isTip ? "tip" : "chat",
                                tip_amount: tipAmount
                            })
                        });
                    }
                }
            }
        } catch (e) { }
    }

    // Attach MutationObserver for instantaneous live chat relay to Discord (Debounced)
    try {
        var scanDebounceTimer = null;
        var chatDomObserver = new MutationObserver(function () {
            if (scanDebounceTimer) return;
            scanDebounceTimer = setTimeout(function () {
                scanDebounceTimer = null;
                scanLiveChatDOM();
            }, 300);
        });
        if (pageDoc && pageDoc.body) {
            chatDomObserver.observe(pageDoc.body, { childList: true, subtree: true });
        } else if (pageDoc) {
            pageDoc.addEventListener("DOMContentLoaded", function () {
                chatDomObserver.observe(pageDoc.body, { childList: true, subtree: true });
            });
        }
    } catch (e) { }

    // ─── Interactive Glassmorphism Control Dock ──────────────────
    let badge = null;
    let badgeContainer = null;
    let isBadgeExpanded = false;

    function updateBadgeUI() {
        if (!badge) return;
        var modelSelect = pageDoc.getElementById("f2f-model-select");
        var camSelect = pageDoc.getElementById("f2f-cam-select");
        var statusSpan = pageDoc.getElementById("f2f-agent-status");
        var shieldSpan = pageDoc.getElementById("f2f-shield-status");

        if (modelSelect && modelSelect.value !== activeCreator) {
            modelSelect.value = activeCreator;
        }

        // Populate camera options
        if (camSelect) {
            var currentVal = targetCameraName;
            var optsHtml = "";
            var knownPresets = ["OBS Cam 0", "OBS Cam 1", "OBS Cam 2", "OBS Cam 3", "OBS Cam 4"];

            // Add detected devices
            if (detectedVideoDevices && detectedVideoDevices.length > 0) {
                optsHtml += `<optgroup label="Detected Cameras">`;
                detectedVideoDevices.forEach(function (d) {
                    if (d.label) {
                        optsHtml += `<option value="${d.label}">${d.label}</option>`;
                    }
                });
                optsHtml += `</optgroup>`;
            }

            optsHtml += `<optgroup label="Presets">`;
            knownPresets.forEach(function (p) {
                optsHtml += `<option value="${p}">${p}</option>`;
            });
            optsHtml += `</optgroup>`;

            camSelect.innerHTML = optsHtml;
            camSelect.value = currentVal;
        }

        // Check if target camera is currently online
        var isCameraOnline = detectedVideoDevices.some(function (d) {
            if (!d.label) return false;
            var lbl = d.label.toLowerCase();
            return lbl.includes(targetCameraName.toLowerCase()) ||
                (creatorCfg.cameraKeywords && creatorCfg.cameraKeywords.some(function (kw) { return lbl.includes(kw); }));
        });

        if (shieldSpan) {
            if (isCameraOnline) {
                shieldSpan.innerHTML = `<span style="color: #10b981; font-weight: bold;">🎥 ${targetCameraName} Online</span>`;
                badge.style.borderColor = "#10b981";
            } else {
                shieldSpan.innerHTML = `<span style="color: #ef4444; font-weight: bold;">🛑 ${targetCameraName} Offline</span>`;
                badge.style.borderColor = "#ef4444";
            }
        }

        var summaryText = pageDoc.getElementById("f2f-badge-summary");
        if (summaryText) {
            var icon = isCameraOnline ? "🟢" : "🛑";
            summaryText.innerHTML = `${icon} <b>${creatorCfg.handle}</b> &nbsp;|&nbsp; 🎥 ${targetCameraName} &nbsp;|&nbsp; Port ${agentPort}`;
        }
    }

    function ensureBadge() {
        if (!pageDoc.body) return;
        if (pageDoc.getElementById("obs-f2f-sync-badge")) {
            badge = pageDoc.getElementById("obs-f2f-sync-badge");
            return;
        }

        badge = pageDoc.createElement("div");
        badge.id = "obs-f2f-sync-badge";

        var savedPos = null;
        try {
            savedPos = JSON.parse(localStorage.getItem("f2f_badge_pos"));
        } catch (e) { }

        Object.assign(badge.style, {
            position: "fixed",
            background: "rgba(15, 23, 42, 0.95)",
            backdropFilter: "blur(12px)",
            color: "#f8fafc",
            padding: "8px 14px", borderRadius: "14px",
            fontSize: "12px", zIndex: "9999999",
            border: "2px solid #10b981",
            boxShadow: "0 10px 35px rgba(0,0,0,0.8)",
            fontFamily: "system-ui, -apple-system, sans-serif",
            userSelect: "none",
            transition: "box-shadow 0.2s ease, border-color 0.2s ease",
            maxWidth: "380px"
        });

        if (savedPos && typeof savedPos.left === "number" && typeof savedPos.top === "number") {
            var validLeft = Math.max(8, Math.min((pageWindow.innerWidth || 1280) - 260, savedPos.left));
            var validTop = Math.max(8, Math.min((pageWindow.innerHeight || 720) - 50, savedPos.top));
            badge.style.left = validLeft + "px";
            badge.style.top = validTop + "px";
            badge.style.bottom = "auto";
            badge.style.right = "auto";
        } else {
            // Default position: bottom-right to never obstruct top navigation tabs or search
            badge.style.bottom = "18px";
            badge.style.right = "18px";
            badge.style.left = "auto";
            badge.style.top = "auto";
        }

        var html = `
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; cursor: grab;" id="f2f-badge-header" title="Drag to move, click to toggle controls, double-click to reset">
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="opacity: 0.5; font-size: 13px; cursor: grab;" title="Drag to move">⠿</span>
                    <span id="f2f-badge-summary" style="font-weight: 600; font-size: 12.5px; white-space: nowrap;">
                        🟢 <b>${creatorCfg.handle}</b> &nbsp;|&nbsp; 🎥 ${targetCameraName} &nbsp;|&nbsp; Port ${agentPort}
                    </span>
                </div>
                <span id="f2f-badge-toggle" style="font-size: 11px; opacity: 0.85; background: rgba(255,255,255,0.12); padding: 3px 8px; border-radius: 8px; cursor: pointer; white-space: nowrap;">⚙️ Controls</span>
            </div>
            <div id="f2f-badge-body" style="display: none; margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.15); flex-direction: column; gap: 8px;">
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                    <label style="font-size: 11px; font-weight: bold; color: #94a3b8;">👤 Active Model:</label>
                    <select id="f2f-model-select" style="background: #1e293b; color: #f8fafc; border: 1px solid #475569; padding: 4px 8px; border-radius: 8px; font-size: 12px; font-weight: bold; cursor: pointer;">
                        <option value="xsophiex">@xsophiex (Port 8081 - Cam 0)</option>
                        <option value="chantalkuyt">@chantalkuyt (Port 8082 - Cam 2)</option>
                        <option value="aylen">@aylen (Port 8083 - Cam 3)</option>
                        <option value="zoelynn">@zoelynn (Port 8084 - Cam 1)</option>
                    </select>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                    <label style="font-size: 11px; font-weight: bold; color: #94a3b8;">🎥 Target Camera:</label>
                    <select id="f2f-cam-select" style="background: #1e293b; color: #f8fafc; border: 1px solid #475569; padding: 4px 8px; border-radius: 8px; font-size: 12px; font-weight: bold; cursor: pointer;">
                    </select>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between; font-size: 11px; margin-top: 4px;">
                    <span id="f2f-agent-status">Checking...</span>
                    <span id="f2f-shield-status">Checking...</span>
                </div>
                <div style="display: flex; gap: 8px; margin-top: 6px;">
                    <button id="f2f-btn-rescan" style="flex: 1; background: #3b82f6; color: white; border: none; padding: 6px 10px; border-radius: 8px; font-weight: bold; font-size: 11px; cursor: pointer;">🔄 Rescan Devices</button>
                    <button id="f2f-btn-test-live" style="flex: 1; background: #10b981; color: white; border: none; padding: 6px 10px; border-radius: 8px; font-weight: bold; font-size: 11px; cursor: pointer;">🧪 Test Go Live</button>
                </div>
            </div>
        `;
        badge.innerHTML = html;
        pageDoc.body.appendChild(badge);

        var header = pageDoc.getElementById("f2f-badge-header");
        var body = pageDoc.getElementById("f2f-badge-body");

        // Drag-and-drop repositioning logic with localStorage persistence
        var isDragging = false;
        var hasMoved = false;
        var dragStartX = 0, dragStartY = 0;
        var startLeft = 0, startTop = 0;

        header.addEventListener("mousedown", function (e) {
            if (e.target.closest("select, button, input") || e.target.id === "f2f-badge-toggle") {
                return;
            }
            isDragging = true;
            hasMoved = false;
            dragStartX = e.clientX;
            dragStartY = e.clientY;

            var rect = badge.getBoundingClientRect();
            startLeft = rect.left;
            startTop = rect.top;

            badge.style.transition = "none";
            header.style.cursor = "grabbing";

            function onMouseMove(moveEvent) {
                if (!isDragging) return;
                var dx = moveEvent.clientX - dragStartX;
                var dy = moveEvent.clientY - dragStartY;
                if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
                    hasMoved = true;
                }
                if (hasMoved) {
                    var winW = pageWindow.innerWidth || 1280;
                    var winH = pageWindow.innerHeight || 720;
                    var newLeft = Math.max(6, Math.min(winW - rect.width - 6, startLeft + dx));
                    var newTop = Math.max(6, Math.min(winH - rect.height - 6, startTop + dy));
                    badge.style.left = newLeft + "px";
                    badge.style.top = newTop + "px";
                    badge.style.bottom = "auto";
                    badge.style.right = "auto";
                }
            }

            function onMouseUp() {
                if (!isDragging) return;
                isDragging = false;
                header.style.cursor = "grab";
                badge.style.transition = "box-shadow 0.2s ease, border-color 0.2s ease";
                pageDoc.removeEventListener("mousemove", onMouseMove);
                pageDoc.removeEventListener("mouseup", onMouseUp);

                if (hasMoved) {
                    var finalRect = badge.getBoundingClientRect();
                    try {
                        localStorage.setItem("f2f_badge_pos", JSON.stringify({ left: Math.round(finalRect.left), top: Math.round(finalRect.top) }));
                    } catch (e) { }
                }
            }

            pageDoc.addEventListener("mousemove", onMouseMove);
            pageDoc.addEventListener("mouseup", onMouseUp);
        });

        // Header click: toggle expanded controls (only if not dragged)
        header.addEventListener("click", function (e) {
            if (hasMoved) {
                hasMoved = false;
                return;
            }
            isBadgeExpanded = !isBadgeExpanded;
            body.style.display = isBadgeExpanded ? "flex" : "none";

            if (isBadgeExpanded) {
                setTimeout(function () {
                    var rect = badge.getBoundingClientRect();
                    var winH = pageWindow.innerHeight || 720;
                    if (rect.bottom > winH - 8) {
                        var adjustedTop = Math.max(8, winH - rect.height - 12);
                        badge.style.top = adjustedTop + "px";
                        badge.style.bottom = "auto";
                    }
                }, 10);
            }
        });

        // Double-click header: reset to default bottom-right position
        header.addEventListener("dblclick", function (e) {
            e.stopPropagation();
            try {
                localStorage.removeItem("f2f_badge_pos");
            } catch (e) { }
            badge.style.bottom = "18px";
            badge.style.right = "18px";
            badge.style.left = "auto";
            badge.style.top = "auto";
            console.log("[F2F-OBS] 📍 Badge position reset to default (bottom-right).");
        });

        // Model Select change handler
        var mSel = pageDoc.getElementById("f2f-model-select");
        mSel.addEventListener("change", function (e) {
            var chosenKey = e.target.value;
            if (CREATORS[chosenKey]) {
                activeCreator = chosenKey;
                creatorCfg = CREATORS[chosenKey];
                agentPort = creatorCfg.port;
                targetCameraName = localStorage.getItem("f2f_target_camera_" + activeCreator) || creatorCfg.defaultCamera;
                localStorage.setItem("f2f_active_creator", activeCreator);
                console.log("%c[F2F-OBS] 👤 Switched Profile to @" + activeCreator + " | Target Camera: " + targetCameraName, "color: #10b981; font-weight: bold;");
                isConnected = false;
                updateBadgeUI();
            }
        });

        // Camera Select change handler
        var cSel = pageDoc.getElementById("f2f-cam-select");
        cSel.addEventListener("change", function (e) {
            targetCameraName = e.target.value;
            localStorage.setItem("f2f_target_camera_" + activeCreator, targetCameraName);
            console.log("%c[F2F-OBS] 🎥 User Locked Target Camera: " + targetCameraName, "color: #10b981; font-weight: bold;");
            updateBadgeUI();
        });

        // Rescan button
        var rescanBtn = pageDoc.getElementById("f2f-btn-rescan");
        rescanBtn.addEventListener("click", async function (e) {
            e.stopPropagation();
            if (pageWindow.navigator && pageWindow.navigator.mediaDevices) {
                var devs = await origEnumerateDevices();
                detectedVideoDevices = devs.filter(function (d) { return d.kind === "videoinput"; });
                console.log("%c[F2F-OBS] 🔄 Rescanned Video Devices:", "color: #3b82f6; font-weight: bold;", detectedVideoDevices.map(function (d) { return d.label; }));
                updateBadgeUI();
            }
        });

        // Test button
        var testBtn = pageDoc.getElementById("f2f-btn-test-live");
        testBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            executeGoLive("In mijn DM ben ik stouter... 😈", "Welcome to the live stream! 💕", "50");
        });

        updateBadgeUI();
    }
    setInterval(ensureBadge, 1000);
    setInterval(updateBadgeUI, 2000);

    // ─── Auto-Dismiss Modals ──────────────────────────────────────
    function autoDismissModals() {
        var allButtons = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
        var gotItBtn = allButtons.find(function (b) {
            var txt = (b.innerText || b.textContent || "").trim().toLowerCase();
            return txt === "got it" || txt === "begrepen" || txt.includes("got it");
        });
        if (gotItBtn) {
            console.log("[F2F-OBS] 📸 Auto-dismissing 'Allow camera' modal...");
            gotItBtn.click();
        }
    }
    setInterval(autoDismissModals, 400);

    // ─── Click via React Fiber & Full DOM Event Cascade ───────────
    function clickElementViaReact(btn) {
        if (!btn) return false;

        // 1. React Props onClick
        try {
            var propsKey = Object.keys(btn).find(function (k) { return k.startsWith("__reactProps$"); });
            if (propsKey && btn[propsKey] && typeof btn[propsKey].onClick === "function") {
                btn[propsKey].onClick({ preventDefault: function () { }, stopPropagation: function () { } });
            }
        } catch (e) { }

        // 2. React Fiber tree walk
        try {
            var fiberKey = Object.keys(btn).find(function (k) {
                return k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$");
            });
            if (fiberKey) {
                var fiber = btn[fiberKey];
                var depth = 0;
                while (fiber && depth < 20) {
                    if (fiber.memoizedProps && typeof fiber.memoizedProps.onClick === "function") {
                        fiber.memoizedProps.onClick({ preventDefault: function () { }, stopPropagation: function () { } });
                        break;
                    }
                    if (fiber.pendingProps && typeof fiber.pendingProps.onClick === "function") {
                        fiber.pendingProps.onClick({ preventDefault: function () { }, stopPropagation: function () { } });
                        break;
                    }
                    fiber = fiber.return;
                    depth++;
                }
            }
        } catch (e) { }

        // 3. Full DOM MouseEvent Cascade
        try {
            btn.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
            btn.click();
        } catch (e) { }
        return true;
    }

    // ─── Find & Click Camera Button ───────────────────────────────
    function findCameraButton() {
        var container = pageDoc.querySelector("div[class*='livestreamPlayerActions'], div[class*='vjx7qW_livestreamPlayerActions']");
        if (container) {
            var actionBtns = Array.from(container.querySelectorAll("div[class*='actionButton'], div[class*='vjx7qW_actionButton'], button, div[role='button']"));
            if (actionBtns.length >= 1) {
                for (var b of actionBtns) {
                    var html = (b.innerHTML || "").toLowerCase();
                    if (html.includes("cam") || html.includes("video") || html.includes("m15") || html.includes("svg")) {
                        return b;
                    }
                }
                return actionBtns[0];
            }
        }
        var all = Array.from(pageDoc.querySelectorAll("div[class*='actionButton'], div[class*='vjx7qW_actionButton'], button[aria-label*='cam' i], button[title*='cam' i]"));
        if (all.length >= 1) return all[0];
        return null;
    }

    function clickCameraButton() {
        var btn = findCameraButton();
        if (!btn) {
            console.warn("[F2F-OBS] ⚠️ Camera toggle button not found!");
            return false;
        }
        console.log("[F2F-OBS] 📷 Toggling Camera Button in player controls...", btn);
        clickElementViaReact(btn);
        return true;
    }

    // ─── Start Live Stream Automation (Go Live) ───────────────────
    function executeGoLive(title, message, tipGoal) {
        console.log("[F2F-OBS] 🚀 executeGoLive invoked:", { title, message, tipGoal, path: pageWindow.location.pathname });

        if (!pageWindow.location.pathname.startsWith("/live")) {
            console.log("[F2F-OBS] 📍 Current tab not on /live/ page. Navigating to https://f2f.com/live/ ...");
            pageWindow.location.href = "https://f2f.com/live/";
            return;
        }

        autoDismissModals();

        if (badge) {
            badge.style.color = "#f59e0b";
            badge.style.borderColor = "#f59e0b";
            var sum = pageDoc.getElementById("f2f-badge-summary");
            if (sum) sum.innerHTML = "⏳ <b>Going Live...</b> &nbsp;|&nbsp; Filling Form";
        }

        var attempts = 0;
        var maxAttempts = 35;
        var targetTitle = title || "In mijn DM ben ik stouter... 😈";

        var interval = setInterval(function () {
            attempts++;
            autoDismissModals();

            var titleInp = findTitleInput();
            var msgInp = findMessageInput();
            var goalInp = findGoalInput();

            var allButtons = Array.from(pageDoc.querySelectorAll("button, div[role='button'], div[class*='Button']"));
            var goLiveBtn = allButtons.find(function (b) {
                var txt = (b.innerText || b.textContent || "").toLowerCase();
                return txt.includes("go live") || txt.includes("live gaan");
            });

            if (titleInp) fillInput(titleInp, targetTitle);
            if (msgInp && message) fillInput(msgInp, message);
            if (goalInp && tipGoal) fillInput(goalInp, tipGoal);

            var isTitleReady = titleInp && titleInp.value && titleInp.value.length > 0;

            if (goLiveBtn && isTitleReady) {
                clearInterval(interval);
                console.log("[F2F-OBS] ✅ Live form ready! Title locked: '" + titleInp.value + "'. Submitting in 400ms...");
                setTimeout(function () {
                    autoDismissModals();
                    fillInput(titleInp, targetTitle);
                    clickElementViaReact(goLiveBtn);
                    try { goLiveBtn.click(); } catch (e) { }
                    console.log("[F2F-OBS] 🎯 Clicked 'Go live'!");
                    if (badge) {
                        badge.style.color = "#10b981";
                        badge.style.borderColor = "#10b981";
                        var sum = pageDoc.getElementById("f2f-badge-summary");
                        if (sum) sum.innerHTML = "🚀 <b>Went Live on F2F!</b>";
                        setTimeout(updateBadgeUI, 4000);
                    }

                    // If Creator is in Camera Offline Mode, automatically turn off camera once player loads!
                    if (creatorCfg && creatorCfg.cameraOfflineMode) {
                        console.log("[F2F-OBS] 📷 Waiting for livestream player to toggle camera offline natively...");
                        var checkCount = 0;
                        var camTogglePoll = setInterval(function () {
                            checkCount++;
                            var camBtn = findCameraButton();
                            if (camBtn) {
                                clearInterval(camTogglePoll);
                                console.log("[F2F-OBS] 🎯 Livestream player ready! Toggling camera button OFF natively...");
                                setTimeout(function () {
                                    clickCameraButton();
                                    if (badge) {
                                        var sum = pageDoc.getElementById("f2f-badge-summary");
                                        if (sum) sum.innerHTML = `📷 <b>${creatorCfg.handle}</b> Camera Offline (Native Avatar)`;
                                    }
                                }, 600);
                            } else if (checkCount >= 30) {
                                clearInterval(camTogglePoll);
                                console.warn("[F2F-OBS] ⚠️ Timed out waiting for player camera button.");
                            }
                        }, 500);
                    }
                }, 400);
            } else if (attempts >= maxAttempts) {
                clearInterval(interval);
                console.warn("[F2F-OBS] ⚠️ Timed out searching for live form.");
                if (badge) {
                    badge.style.color = "#ef4444";
                    badge.style.borderColor = "#ef4444";
                    var sum = pageDoc.getElementById("f2f-badge-summary");
                    if (sum) sum.innerHTML = "⚠️ <b>Timed out</b> finding form";
                }
            }
        }, 500);
    }

    // ─── Multi-Strategy Input Finders ─────────────────────────────
    function findTitleInput() {
        var allInputs = Array.from(pageDoc.querySelectorAll("input:not([type='hidden']):not([type='checkbox']):not([type='radio'])"));
        for (var inp of allInputs) {
            var ph = (inp.placeholder || inp.getAttribute("placeholder") || inp.getAttribute("aria-label") || inp.name || inp.id || "").toLowerCase();
            if (ph.includes("title") || ph.includes("titel") || ph.includes("live title")) return inp;
        }
        for (var inp of allInputs) {
            var parent = inp.closest("div[class*='input'], div[class*='Field'], div[class*='group'], section, form, div");
            if (parent) {
                var txt = (parent.innerText || parent.textContent || "").toLowerCase();
                if ((txt.includes("title") || txt.includes("details")) && !txt.includes("goal")) return inp;
            }
        }
        var textInputs = allInputs.filter(function (i) {
            var ph = (i.placeholder || i.getAttribute("placeholder") || "").toLowerCase();
            return !ph.includes("goal") && !ph.includes("doel") && (i.type === "text" || !i.type || i.type === "search");
        });
        if (textInputs.length > 0) return textInputs[textInputs.length - 1];
        return null;
    }

    function findMessageInput() {
        var textarea = pageDoc.querySelector("textarea");
        if (textarea) return textarea;
        var allInputs = Array.from(pageDoc.querySelectorAll("input:not([type='hidden'])"));
        for (var inp of allInputs) {
            var ph = (inp.placeholder || inp.getAttribute("placeholder") || "").toLowerCase();
            if (ph.includes("message") || ph.includes("bericht")) return inp;
        }
        return null;
    }

    function findGoalInput() {
        var allInputs = Array.from(pageDoc.querySelectorAll("input:not([type='hidden'])"));
        for (var inp of allInputs) {
            var ph = (inp.placeholder || inp.getAttribute("placeholder") || "").toLowerCase();
            if (ph.includes("goal") || ph.includes("doel") || ph.includes("set")) return inp;
        }
        return null;
    }

    function fillInput(input, value) {
        if (!input || !value) return false;
        input.focus();
        try { input.click(); } catch (e) { }
        try { if (input._valueTracker) input._valueTracker.setValue(""); } catch (e) { }
        try {
            var proto = input.tagName === "TEXTAREA"
                ? (pageWindow.HTMLTextAreaElement ? pageWindow.HTMLTextAreaElement.prototype : Object.getPrototypeOf(input))
                : (pageWindow.HTMLInputElement ? pageWindow.HTMLInputElement.prototype : Object.getPrototypeOf(input));
            var descriptor = Object.getOwnPropertyDescriptor(proto, "value");
            if (descriptor && descriptor.set) descriptor.set.call(input, value); else input.value = value;
        } catch (e) { input.value = value; }
        try {
            input.dispatchEvent(new pageWindow.InputEvent("input", { bubbles: true, cancelable: true, inputType: "insertText", data: value }));
            input.dispatchEvent(new pageWindow.Event("input", { bubbles: true, cancelable: true }));
            input.dispatchEvent(new pageWindow.Event("change", { bubbles: true, cancelable: true }));
        } catch (e) { }
        return (input.value === value || input.value.length > 0);
    }

    // ─── End Live Stream Automation (Bulletproof & Closes Tab) ───
    function closeCurrentTab() {
        console.log("[F2F-OBS] 🛑 Closing F2F Live tab cleanly...");
        seenMessageIds.clear();
        if (liveSocket) {
            try { liveSocket.close(); } catch (e) { }
        }
        if (badge) {
            badge.style.color = "#ef4444";
            badge.style.borderColor = "#ef4444";
            var sum = pageDoc.getElementById("f2f-badge-summary");
            if (sum) sum.innerHTML = "🛑 <b>Stream Ended</b> — Closing Tab...";
        }

        // 1. Privileged userscript close
        try { window.close(); } catch (e) { }
        try { unsafeWindow.close(); } catch (e) { }
        try { pageWindow.close(); } catch (e) { }

        // 2. Cascade fallback: replace with about:blank and close
        setTimeout(function () {
            try { window.close(); } catch (e) { }
            try { pageWindow.location.replace("about:blank"); } catch (e) { }
            setTimeout(function () {
                try { window.close(); } catch (e) { }
                try { unsafeWindow.close(); } catch (e) { }
            }, 150);
        }, 300);
    }

    function executeEndStream() {
        console.log("[F2F-OBS] 🛑 Ending current livestream from Discord...");
        hasToggledOfflineCamera = false;
        autoDismissModals();

        // 1. Check if live exit button exists (when currently broadcasting)
        var exitBtn = pageDoc.querySelector("div[class*='logoutIcon'], div[class*='logout'], div[class*='vjx7qW_logoutIcon'], div[class*='exitIcon'], button[class*='logout'], button[class*='exit'], [aria-label*='exit' i], [aria-label*='stop' i], [aria-label*='end' i]");
        if (!exitBtn) {
            var container = pageDoc.querySelector("div[class*='livestreamPlayerActions'], div[class*='vjx7qW_livestreamPlayerActions']");
            if (container) {
                var btns = Array.from(container.querySelectorAll("div[class*='actionButton'], div[class*='logoutIcon'], div[role='button'], button"));
                if (btns.length >= 2) exitBtn = btns[btns.length - 1];
            }
        }

        if (exitBtn) {
            console.log("[F2F-OBS] 🎯 Clicking live stream exit button...");
            clickElementViaReact(exitBtn);
            try { exitBtn.click(); } catch (e) { }

            var confirmAttempts = 0;
            var confirmInterval = setInterval(function () {
                confirmAttempts++;
                var confirmBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
                var endConfirm = confirmBtns.find(function (b) {
                    var txt = (b.innerText || b.textContent || "").trim().toLowerCase();
                    return (txt.includes("end") || txt.includes("yes") || txt.includes("confirm") || txt.includes("beëindigen") || txt.includes("stop")) && !txt.includes("go live") && !txt.includes("live gaan");
                });
                if (endConfirm && endConfirm !== exitBtn) {
                    clearInterval(confirmInterval);
                    console.log("[F2F-OBS] 🎯 Confirming stream termination...");
                    clickElementViaReact(endConfirm);
                    try { endConfirm.click(); } catch (e) { }
                    setTimeout(closeCurrentTab, 1000);
                } else if (confirmAttempts >= 10) {
                    clearInterval(confirmInterval);
                    closeCurrentTab();
                }
            }, 200);
        } else {
            console.log("[F2F-OBS] ℹ️ Stream is not actively broadcasting (or on setup/error screen). Closing tab immediately...");
            closeCurrentTab();
        }
    }

    // ─── Live Chat: Send & Delete ─────────────────────────────────
    function sendLiveChatMessage(text) {
        console.log("[F2F-OBS] 💬 Processing Live Chat dispatch from Discord:", text);
        if (liveSocket && liveSocket.readyState === 1) {
            var channel = activeChannelName || window.location.pathname.replace(/\//g, "") || "stream";
            try {
                liveSocket.send("42" + JSON.stringify(["livestream:chat:message:send", [channel, text]]));
                console.log("[F2F-OBS] ⚡ Sent live chat message via socket:", text);
            } catch (e) { }
        }
        var inputs = Array.from(pageDoc.querySelectorAll("textarea, input:not([type='hidden'])"));
        var chatInput = inputs.find(function (inp) {
            var ph = (inp.placeholder || inp.getAttribute("placeholder") || inp.getAttribute("aria-label") || "").toLowerCase();
            return ph.includes("say") || ph.includes("comment") || ph.includes("chat") || ph.includes("message") || ph.includes("bericht") || ph.includes("type");
        });
        if (!chatInput) {
            var textInputs = inputs.filter(function (i) { return i.type === "text" || !i.type || i.tagName === "TEXTAREA"; });
            if (textInputs.length > 0) chatInput = textInputs[textInputs.length - 1];
        }
        if (chatInput) {
            fillInput(chatInput, text);
            var enterOpts = { key: "Enter", code: "Enter", which: 13, keyCode: 13, bubbles: true, cancelable: true };
            chatInput.dispatchEvent(new pageWindow.KeyboardEvent("keydown", enterOpts));
            chatInput.dispatchEvent(new pageWindow.KeyboardEvent("keypress", enterOpts));
            chatInput.dispatchEvent(new pageWindow.KeyboardEvent("keyup", enterOpts));
            var container = chatInput.closest("form, div[class*='chat'], div[class*='input'], div[class*='Footer'], div");
            if (container) {
                var sendBtn = container.querySelector("button[type='submit'], button, div[role='button'], svg");
                if (sendBtn && sendBtn !== chatInput) {
                    clickElementViaReact(sendBtn);
                    try { sendBtn.click(); } catch (e) { }
                }
            }
        }
        ensureChatScrolledToBottom();
        setTimeout(ensureChatScrolledToBottom, 150);
        setTimeout(ensureChatScrolledToBottom, 500);
    }

    function logToAgent(tag, message, data) {
        console.log(`[F2F-OBS] [${tag}]`, message, data || "");
        try {
            GM_xmlhttpRequest({
                method: "POST",
                url: "http://127.0.0.1:" + agentPort + "/api/incoming-chat",
                headers: { "Content-Type": "application/json" },
                data: JSON.stringify({
                    type: "log",
                    username: "[" + tag + "]",
                    text: String(message) + (data ? (" " + JSON.stringify(data)) : "")
                })
            });
        } catch (e) { }
    }

    function dispatchWebSocketDelete(messageId, channel) {
        if (!liveSocket || liveSocket.readyState !== 1 || !messageId) return;
        var rawId = String(messageId).trim();
        if (rawId.includes(":")) return; // skip fake DOM hashes
        var ch = (rawId.includes("#")) ? rawId.split("#")[0] : (channel || activeChannelName || "stream");
        var shortId = (rawId.includes("#")) ? rawId.split("#")[1] : rawId;
        try {
            liveSocket.send("42" + JSON.stringify(["livestream:chat:message:delete", ch, shortId]));
            if (shortId !== rawId) {
                liveSocket.send("42" + JSON.stringify(["livestream:chat:message:delete", ch, rawId]));
            }
            logToAgent("SOCKET_DELETE", "Sent delete packet for ID:", { ch, shortId });
        } catch (e) { }
    }

    function dispatchWebSocketBlock(cleanUser, channel) {
        if (!liveSocket || liveSocket.readyState !== 1 || !cleanUser) return;
        var ch = channel || activeChannelName || "stream";
        try {
            liveSocket.send("42" + JSON.stringify(["livestream:chat:user:block", ch, cleanUser]));
            liveSocket.send("42" + JSON.stringify(["livestream:chat:user:ban", ch, cleanUser]));
            logToAgent("SOCKET_BAN", "Sent ban/block packets for:", { ch, cleanUser });
        } catch (e) { }
    }

    function formatUUID(str) {
        if (!str) return "";
        var clean = str.replace(/-/g, "");
        if (clean.length === 32) {
            return clean.slice(0, 8) + "-" + clean.slice(8, 12) + "-" + clean.slice(12, 16) + "-" + clean.slice(16, 20) + "-" + clean.slice(20);
        }
        return str;
    }

    function dispatchAuthenticatedBanAPIs(cleanUser) {
        if (!cleanUser) return;
        try {
            var csrfMatch = pageDoc.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
            var csrfToken = csrfMatch ? decodeURIComponent(csrfMatch[1]) : "";
            var headers = {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            };

            var creatorHandle = (activeCreator || "xsophiex").replace(/^@/, "");
            var liveUuid = "";
            if (activeChannelName && activeChannelName.includes("-")) {
                var parts = activeChannelName.split("-");
                liveUuid = parts[parts.length - 1];
            }

            // 1. Primary: Direct block on creator account settings (Verified 200 OK!)
            pageWindow.fetch("/api/creators/" + creatorHandle + "/banned-users/", {
                method: "POST",
                headers: headers,
                body: JSON.stringify({ username: cleanUser })
            }).then(function (r) {
                logToAgent("API_BAN", "/api/creators/.../banned-users status: " + r.status);
            }).catch(function (e) { });

            // 2. Livestream viewer ban with RFC 4122 hyphenated UUID
            pageWindow.fetch("/api/creators/" + creatorHandle + "/livestream/", {
                headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" }
            }).then(function (r) { return r.json(); }).then(function (liveData) {
                var rawUuid = liveData.uuid || liveData.id || liveUuid;
                var uuid = formatUUID(rawUuid);
                if (uuid) {
                    pageWindow.fetch("/api/livestreams/" + uuid + "/viewers/" + cleanUser + "/ban/", {
                        method: "POST",
                        headers: headers
                    }).then(function (r) {
                        logToAgent("API_BAN", "/api/livestreams/.../ban status: " + r.status);
                    }).catch(function (e) { });
                }
            }).catch(function (e) { });
        } catch (e) {
            logToAgent("API_BAN_ERR", "Exception: " + e.message);
        }
    }

    function findChatRowAndTriggerAction(username, text, action) {
        var cleanUser = (username || "").replace(/^@/, "").replace(/[\n\r]+/g, " ").replace(/\b(Follower|Subscriber|VIP|Moderator)\b/gi, "").trim().toLowerCase();
        var cleanText = (text || "").split("\n")[0].trim().toLowerCase();
        if (cleanText.length > 50) cleanText = cleanText.substring(0, 50);

        var handleClean = (activeCreator || "").toLowerCase().replace(/[@\s]/g, "");
        var isCreator = cleanUser && (cleanUser.includes(handleClean) || handleClean.includes(cleanUser) || cleanUser.includes("sophie") || cleanUser.includes("chantal") || cleanUser.includes("zoe") || cleanUser.includes("aylen"));

        logToAgent("DOM_" + action.toUpperCase(), "Searching row for user: " + cleanUser + ", text: " + cleanText + " (isCreator=" + isCreator + ")");

        var allLeafs = Array.from(pageDoc.querySelectorAll("span, div, p, li, b, strong, a")).filter(function (el) {
            return el.children.length === 0 && (el.innerText || el.textContent || "").trim().length > 0;
        });

        var matchingElements = [];
        if (cleanText) {
            var textMatches = allLeafs.filter(function (el) {
                var t = (el.innerText || el.textContent || "").trim().toLowerCase();
                return t === cleanText || (cleanText.length >= 3 && (t.includes(cleanText) || cleanText.includes(t)));
            });
            matchingElements = matchingElements.concat(textMatches);
        }
        if (matchingElements.length === 0 && cleanUser) {
            var userMatches = allLeafs.filter(function (el) {
                var t = (el.innerText || el.textContent || "").trim().toLowerCase();
                return t === cleanUser || t === "@" + cleanUser || t.startsWith(cleanUser) || cleanUser.startsWith(t);
            });
            matchingElements = matchingElements.concat(userMatches);
        }

        if (matchingElements.length === 0) {
            logToAgent("DOM_" + action.toUpperCase(), "No matching leaf elements found for: " + cleanUser + " / " + cleanText);
            return false;
        }

        for (var el of matchingElements) {
            var curr = el;
            var chatRow = null;

            // 1. Primary: Walk up to find a known chat row class
            for (var i = 0; i < 8; i++) {
                if (!curr || curr === pageDoc.body || !curr.parentElement) break;
                if (curr.className && typeof curr.className === "string" && /Tc9FFW_message|message|chatMessage|MessageItem/i.test(curr.className)) {
                    chatRow = curr;
                    break;
                }
                curr = curr.parentElement;
            }

            // 2. Fallback: Walk up for LI or container with button/svg
            if (!chatRow) {
                curr = el;
                for (var j = 0; j < 6; j++) {
                    if (!curr || curr === pageDoc.body) break;
                    var hasClass = curr.className && typeof curr.className === "string" && curr.className.trim().length > 0;
                    var isRowCandidate = (
                        curr.tagName === "LI" ||
                        (hasClass && /message|comment|chat|item/i.test(curr.className)) ||
                        (hasClass && curr.parentElement && curr.parentElement.children.length > 2 && curr.offsetHeight > 15 && curr.offsetHeight < 250)
                    );
                    if (isRowCandidate && curr.querySelector("button, div[role='button'], svg")) {
                        chatRow = curr;
                        break;
                    }
                    curr = curr.parentElement;
                }
            }

            if (chatRow) {
                logToAgent("DOM_" + action.toUpperCase(), "Found chat row: <" + chatRow.tagName + " class='" + (chatRow.className || "") + "'>");
                chatRow.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true, cancelable: true }));
                chatRow.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, cancelable: true }));
                chatRow.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, cancelable: true }));

                function cleanupHoverAndMenus() {
                    try {
                        chatRow.dispatchEvent(new MouseEvent("mouseleave", { bubbles: true, cancelable: true }));
                        chatRow.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, cancelable: true }));
                        pageDoc.body.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, cancelable: true, clientX: 0, clientY: 0 }));
                    } catch (e) { }
                    ensureChatScrolledToBottom();
                    setTimeout(ensureChatScrolledToBottom, 200);
                }

                var btns = Array.from(chatRow.querySelectorAll("button, div[role='button'], a[role='button'], svg"));

                // CASE A: Direct trash can button on row (especially for creator messages)
                if (action === "delete") {
                    var directTrashBtn = btns.find(function (b) {
                        var cls = (b.getAttribute("class") || "").toLowerCase();
                        var aria = (b.getAttribute("aria-label") || "").toLowerCase();
                        var title = (b.getAttribute("title") || "").toLowerCase();
                        if (cls.includes("trash") || cls.includes("delete") || cls.includes("verwijder") || cls.includes("remove") ||
                            aria.includes("trash") || aria.includes("delete") || aria.includes("remove") || aria.includes("verwijder") ||
                            title.includes("trash") || title.includes("delete") || title.includes("remove") || title.includes("verwijder")) {
                            return true;
                        }
                        var svg = b.tagName === "SVG" ? b : b.querySelector("svg");
                        if (svg) {
                            var svgStr = svg.outerHTML.toLowerCase();
                            if (svgStr.includes("trash") || svgStr.includes("delete") || svgStr.includes("remove") || svgStr.includes("bin") ||
                                svgStr.includes("m19") || svgStr.includes("m6") || svgStr.includes("d=\"m9")) {
                                return true;
                            }
                        }
                        return false;
                    });

                    // If creator message and no explicit trash class found, any clickable button on creator row is the trash button
                    if (!directTrashBtn && isCreator) {
                        var clickables = btns.filter(function (b) {
                            return b.tagName === "BUTTON" || b.getAttribute("role") === "button";
                        });
                        if (clickables.length > 0) {
                            directTrashBtn = clickables[clickables.length - 1];
                        } else if (btns.length > 0) {
                            directTrashBtn = btns[btns.length - 1];
                        }
                    }

                    if (directTrashBtn) {
                        logToAgent("DOM_DELETE", "Found direct trash can button on row -> CLICKING");
                        var clickable = directTrashBtn.closest("button, div[role='button']") || directTrashBtn;
                        clickElementViaReact(clickable);
                        try { clickable.click(); } catch (e) { }

                        var confirmAttempts = 0;
                        var confirmInterval = setInterval(function () {
                            confirmAttempts++;
                            var confirmBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
                            var confirmBtn = confirmBtns.find(function (cb) {
                                var cbt = (cb.innerText || cb.textContent || "").toLowerCase();
                                var isMatch = cbt.includes("delete") || cbt.includes("verwijder") || cbt.includes("remove") || cbt.includes("yes") || cbt.includes("confirm");
                                return isMatch && !cbt.includes("cancel") && !cbt.includes("annul");
                            });
                            if (confirmBtn) {
                                clearInterval(confirmInterval);
                                logToAgent("DOM_DELETE", "Clicking confirmation modal: " + (confirmBtn.innerText || "").trim());
                                clickElementViaReact(confirmBtn);
                                try { confirmBtn.click(); } catch (e) { }
                                setTimeout(cleanupHoverAndMenus, 200);
                            } else if (confirmAttempts >= 15) {
                                clearInterval(confirmInterval);
                                cleanupHoverAndMenus();
                            }
                        }, 100);
                        return true;
                    }
                }

                // CASE B: 3-dots popup menu (for viewer delete or viewer block/ban)
                var moreBtn = btns.find(function (b) {
                    var cls = (b.getAttribute("class") || "").toLowerCase();
                    var aria = (b.getAttribute("aria-label") || "").toLowerCase();
                    var title = (b.getAttribute("title") || "").toLowerCase();
                    return cls.includes("more") || cls.includes("dot") || cls.includes("menu") || cls.includes("action") ||
                        aria.includes("more") || aria.includes("menu") || aria.includes("action") ||
                        title.includes("more") || title.includes("menu") || title.includes("action");
                });

                if (!moreBtn) {
                    var clickableBtns = btns.filter(function (b) {
                        return b.tagName === "BUTTON" || b.getAttribute("role") === "button";
                    });
                    if (clickableBtns.length > 0) {
                        moreBtn = clickableBtns[clickableBtns.length - 1];
                    } else if (btns.length > 0) {
                        moreBtn = btns[btns.length - 1];
                    }
                }

                if (moreBtn) {
                    logToAgent("DOM_" + action.toUpperCase(), "Clicking action/more button");
                    var moreClickable = moreBtn.closest("button, div[role='button']") || moreBtn;
                    clickElementViaReact(moreClickable);
                    try { moreClickable.click(); } catch (e) { }

                    setTimeout(function () {
                        var menuItems = Array.from(pageDoc.querySelectorAll(
                            "button, div[role='menuitem'], div[role='button'], div[class*='menuItem'], div[class*='MenuItem'], div[class*='item'], li, span, a"
                        ));
                        var menuTexts = menuItems.map(function (m) { return (m.innerText || m.textContent || "").trim(); }).filter(function (t) { return t.length > 0 && t.length < 50; });
                        logToAgent("DOM_MENU", "Available popup options for " + action + ":", menuTexts);

                        var targetOption = null;
                        if (action === "delete") {
                            targetOption = menuItems.find(function (m) {
                                var t = (m.innerText || m.textContent || "").trim().toLowerCase();
                                return t.includes("delete") || t.includes("verwijder") || t.includes("remove") || t.includes("trash");
                            });
                        } else {
                            // STRICT BLOCK / BAN ONLY - NEVER MATCH MUTE, UNMUTE, UNBLOCK, OR UNBAN
                            targetOption = menuItems.find(function (m) {
                                var t = (m.innerText || m.textContent || "").trim().toLowerCase();
                                return (t.includes("block") || t.includes("blokkeer") || t.includes("ban")) &&
                                    !t.includes("unblock") && !t.includes("unban") && !t.includes("deblokkeer");
                            });
                        }

                        if (targetOption) {
                            logToAgent("DOM_" + action.toUpperCase(), "Found popup menu option: '" + (targetOption.innerText || "").trim() + "' -> CLICKING");
                            clickElementViaReact(targetOption);
                            try { targetOption.click(); } catch (e) { }

                            var confirmAttempts = 0;
                            var confirmInterval = setInterval(function () {
                                confirmAttempts++;
                                var confirmBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
                                var confirmBtn = confirmBtns.find(function (cb) {
                                    var cbt = (cb.innerText || cb.textContent || "").toLowerCase();
                                    var isMatch = false;
                                    if (action === "delete") {
                                        isMatch = cbt.includes("delete") || cbt.includes("verwijder") || cbt.includes("remove") || cbt.includes("yes") || cbt.includes("confirm");
                                    } else {
                                        isMatch = (cbt.includes("block") || cbt.includes("blokkeer") || cbt.includes("ban") || cbt.includes("yes") || cbt.includes("confirm") || cbt.includes("ok")) &&
                                            !cbt.includes("unblock") && !cbt.includes("unban");
                                    }
                                    return isMatch && !cbt.includes("cancel") && !cbt.includes("annul");
                                });
                                if (confirmBtn) {
                                    clearInterval(confirmInterval);
                                    logToAgent("DOM_" + action.toUpperCase(), "Clicking confirmation modal: " + (confirmBtn.innerText || "").trim());
                                    clickElementViaReact(confirmBtn);
                                    try { confirmBtn.click(); } catch (e) { }
                                    setTimeout(cleanupHoverAndMenus, 200);
                                } else if (confirmAttempts >= 15) {
                                    clearInterval(confirmInterval);
                                    cleanupHoverAndMenus();
                                }
                            }, 100);
                        } else {
                            logToAgent("DOM_" + action.toUpperCase(), "Option for '" + action + "' not found in popup menu");
                            try {
                                pageDoc.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
                                pageDoc.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", code: "Escape", bubbles: true }));
                            } catch (e) { }
                            cleanupHoverAndMenus();
                        }
                    }, 250);
                    return true;
                }
            }
        }
        return false;
    }

    function deleteLiveChatMessage(messageId, text, username) {
        logToAgent("DELETE_START", "Triggered delete", { messageId, text, username });
        if (messageId) {
            dispatchWebSocketDelete(messageId, activeChannelName);
        }
        findChatRowAndTriggerAction(username, text, "delete");
        ensureChatScrolledToBottom();
        setTimeout(ensureChatScrolledToBottom, 150);
        setTimeout(ensureChatScrolledToBottom, 500);
        return true;
    }

    function blockLiveUser(username, text) {
        var cleanUser = (username || "").replace(/^@/, "").replace(/[\n\r]+/g, " ").replace(/\b(Follower|Subscriber|VIP|Moderator)\b/gi, "").trim();
        logToAgent("BLOCK_START", "Triggered block/ban", { cleanUser, text });
        dispatchWebSocketBlock(cleanUser, activeChannelName);
        dispatchAuthenticatedBanAPIs(cleanUser);
        findChatRowAndTriggerAction(cleanUser, text, "block");
        ensureChatScrolledToBottom();
        setTimeout(ensureChatScrolledToBottom, 150);
        setTimeout(ensureChatScrolledToBottom, 500);
        return true;
    }

    // ─── Poll OBS Agent for Events (Strict Port Lock, No Hopping) ──
    var hasToggledOfflineCamera = false;
    function checkAndApplyOfflineCamera() {
        if (!creatorCfg || !creatorCfg.cameraOfflineMode || hasToggledOfflineCamera) return;
        var camBtn = findCameraButton();
        if (camBtn) {
            hasToggledOfflineCamera = true;
            console.log("[F2F-OBS] 🌸 Camera Offline Mode: Auto-toggling camera OFF in active broadcast player...");
            setTimeout(function () {
                clickCameraButton();
            }, 800);
        }
    }

    function pollAgentEvents() {
        ensureBadge();
        ensureChatScrolledToBottom();
        scanLiveChatDOM();
        checkAndApplyOfflineCamera();
        GM_xmlhttpRequest({
            method: "GET",
            url: "http://127.0.0.1:" + agentPort + "/api/camera-event?t=" + Date.now(),
            timeout: 2000,
            onload: function (response) {
                try {
                    var data = JSON.parse(response.responseText);
                    if (!isConnected) {
                        isConnected = true;
                        console.log("[F2F-OBS] ✅ Connected to @" + activeCreator + " OBS Agent on port " + agentPort + "!");
                        updateBadgeUI();
                    }

                    if (data.event_id && data.event_id !== lastProcessedEventId) {
                        lastProcessedEventId = data.event_id;
                        console.log("[F2F-OBS] 🚨 EVENT:", data.action, "event_id:", data.event_id);

                        if (data.action === "turn_camera_off" || data.action === "toggle_camera") {
                            if (badge) {
                                badge.style.color = "#f59e0b";
                                badge.style.borderColor = "#f59e0b";
                                var sum = pageDoc.getElementById("f2f-badge-summary");
                                if (sum) sum.innerHTML = `📷 <b>${creatorCfg.handle}</b> Camera Toggle`;
                            }
                            clickCameraButton();
                        } else if (data.action === "turn_camera_on") {
                            if (badge) {
                                badge.style.color = "#10b981";
                                badge.style.borderColor = "#10b981";
                                var sum = pageDoc.getElementById("f2f-badge-summary");
                                if (sum) sum.innerHTML = `📷 <b>${creatorCfg.handle}</b> Camera ON`;
                            }
                            clickCameraButton();
                            setTimeout(updateBadgeUI, 3000);
                        } else if (data.action === "go_live") {
                            executeGoLive(data.title, data.message, data.tip_goal);
                        } else if (data.action === "end_stream") {
                            executeEndStream();
                        } else if (data.action === "send_chat" && data.chat_message) {
                            sendLiveChatMessage(data.chat_message);
                        } else if (data.action === "delete_chat") {
                            deleteLiveChatMessage(data.delete_message_id, data.delete_text, data.delete_username);
                        } else if (data.action === "block_user") {
                            blockLiveUser(data.block_username, data.block_text);
                        }
                    }
                } catch (e) {
                    console.error("[F2F-OBS] Poll error:", e);
                }
                setTimeout(pollAgentEvents, 400);
            },
            onerror: function () {
                if (isConnected) {
                    isConnected = false;
                    console.warn("[F2F-OBS] ⚠️ Lost connection to @" + activeCreator + " OBS Agent on port " + agentPort);
                    updateBadgeUI();
                }
                setTimeout(pollAgentEvents, 1500);
            },
            ontimeout: function () {
                if (isConnected) {
                    isConnected = false;
                    updateBadgeUI();
                }
                setTimeout(pollAgentEvents, 1000);
            }
        });
    }

    pollAgentEvents();
})();
