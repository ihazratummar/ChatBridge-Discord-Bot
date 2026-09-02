// ==UserScript==
// @name         F2F Live OBS Camera & Chat Automation
// @namespace    http://tampermonkey.net/
// @version      3.5
// @description  Full F2F Live Stream Automation: Instant Double-Event Camera Toggle Engine (Camera ON/OFF), Precision Live Chat Scraper, Bulletproof End Stream, Direct WebSocket Relay, Multi-Strategy Input Finder, React Value Tracker Reset, Auto Port Discovery, Go Live
// @match        https://f2f.com/*
// @match        https://*.f2f.com/*
// @grant        GM_xmlhttpRequest
// @grant        unsafeWindow
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    const pageWindow = unsafeWindow;
    const pageDoc = pageWindow.document;

    console.log("%c[F2F-OBS] v3.5 Instant Camera Toggle & Chat Active", "color: #10b981; font-weight: bold; font-size: 16px;");

    // Dynamic Port Discovery
    var agentPort = 8081;
    var isConnected = false;
    var lastProcessedEventId = 0;
    var candidatePorts = [8081, 8082, 8083, 8084, 8085, 8080];

    var liveSocket = null;
    var activeChannelName = "";
    var seenMessageIds = new Set();

    // ─── Direct WebSocket Hook ────────────────────────────────────
    try {
        if (pageWindow.WebSocket && !pageWindow.__f2f_ws_hooked) {
            pageWindow.__f2f_ws_hooked = true;
            pageWindow.WebSocket = new Proxy(pageWindow.WebSocket, {
                construct(target, args) {
                    var ws = Reflect.construct(target, args);
                    try {
                        var url = args[0];
                        if (typeof url === "string" && (url.includes("socket.f2f.net") || url.includes("f2f.com") || url.includes("socket.io"))) {
                            console.log("%c[F2F-OBS] ⚡ Hooked F2F Live WebSocket: " + url, "color: #3b82f6; font-weight: bold;");
                            liveSocket = ws;

                            ws.addEventListener("message", function(event) {
                                try {
                                    var data = event.data;
                                    if (typeof data !== "string") return;

                                    if (data.startsWith("42")) {
                                        var parsed = JSON.parse(data.substring(2));
                                        var eventName = parsed[0];
                                        var payload = parsed[1];

                                        if (eventName === "livestream:chat:message:sent" && payload) {
                                            var msgId = payload.id || "";
                                            var content = payload.content || payload.message || "";
                                            var userObj = payload.user || {};
                                            var username = userObj.username || userObj.display_name || payload.username || "Fan";
                                            var tipAmount = payload.amount || 0;
                                            var isTip = tipAmount > 0 || (payload.type === "tip");

                                            if (msgId.includes("#")) {
                                                activeChannelName = msgId.split("#")[0];
                                            }

                                            var msgHash = msgId || (username + ":" + content);
                                            if (!seenMessageIds.has(msgHash)) {
                                                seenMessageIds.add(msgHash);
                                                console.log("%c[F2F-OBS] 📥 [WS CHAT] " + username + ": " + content, "color: #10b981; font-weight: bold;");

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
                                        } else if (eventName === "livestream:chat:tip:received" && payload) {
                                            var tipUser = payload.username || payload.display_name || "Fan";
                                            var tipAmt = payload.amount || payload.total_tip_revenue || 0;
                                            console.log("%c[F2F-OBS] 💸 [WS TIP] " + tipUser + ": €" + tipAmt, "color: #f59e0b; font-weight: bold;");
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
                                } catch(e) {}
                            });
                        }
                    } catch(e) {}
                    return ws;
                }
            });
        }
    } catch(e) {}

    // ─── Precision DOM Chat Scraper ───────────────────────────────
    function scanLiveChatDOM() {
        var rootArea = pageDoc.body;
        var allElements = Array.from(rootArea.querySelectorAll("p, div, span, li"));
        for (var el of allElements) {
            var rawText = (el.innerText || el.textContent || "").trim();
            if (!rawText || rawText.length < 3 || rawText.length > 500) continue;
            if (rawText.endsWith("joined") || rawText === "Chat" || rawText === "Follower" || rawText === "Subscriber" || rawText.includes("OBS Sync") || rawText.includes("security will suffer")) continue;

            var lines = rawText.split("\n").map(function(l) { return l.trim(); }).filter(function(l) { return l.length > 0; });
            var username = "";
            var messageText = "";

            if (lines.length >= 2 && lines[0].length < 35) {
                username = lines[0].replace("Follower", "").replace("Subscriber", "").trim();
                messageText = lines.slice(1).join(" ").replace("Follower", "").replace("Subscriber", "").trim();
            } else if (rawText.includes(":") && !rawText.startsWith("http")) {
                var parts = rawText.split(":");
                username = parts[0].trim();
                messageText = parts.slice(1).join(":").trim();
            }

            if (username && messageText && username.length < 35 && messageText.length > 0 && !messageText.endsWith("joined") && messageText !== username) {
                var hash = username + ":" + messageText;
                if (!seenMessageIds.has(hash)) {
                    seenMessageIds.add(hash);
                    console.log("%c[F2F-OBS] 💬 [DOM CHAT CAPTURED] " + username + ": " + messageText, "color: #10b981; font-weight: bold; font-size: 14px;");

                    GM_xmlhttpRequest({
                        method: "POST",
                        url: "http://127.0.0.1:" + agentPort + "/api/incoming-chat",
                        headers: { "Content-Type": "application/json" },
                        data: JSON.stringify({
                            username: username,
                            text: messageText,
                            type: messageText.includes("€") ? "tip" : "chat"
                        })
                    });
                }
            }
        }
    }
    setInterval(scanLiveChatDOM, 800);

    // ─── Badge UI ─────────────────────────────────────────────────
    let badge = null;
    function ensureBadge() {
        if (!pageDoc.body) return;
        if (pageDoc.getElementById("obs-f2f-sync-badge")) {
            badge = pageDoc.getElementById("obs-f2f-sync-badge");
            return;
        }
        badge = pageDoc.createElement("div");
        badge.id = "obs-f2f-sync-badge";
        Object.assign(badge.style, {
            position: "fixed", top: "12px", right: "12px",
            background: "#0f172a", color: "#10b981",
            padding: "10px 18px", borderRadius: "24px",
            fontSize: "13px", fontWeight: "bold", zIndex: "9999999",
            border: "2px solid #10b981", boxShadow: "0 8px 30px rgba(0,0,0,0.7)",
            cursor: "pointer", fontFamily: "system-ui, sans-serif"
        });
        badge.innerText = "🟢 OBS Sync: Port " + agentPort;
        badge.addEventListener("click", function() {
            console.log("[F2F-OBS] 🧪 Manual test trigger clicked!");
            executeGoLive("In mijn DM ben ik stouter... 😈", "Welcome to the live stream! 💕", "50");
        });
        pageDoc.body.appendChild(badge);
    }
    setInterval(ensureBadge, 1000);

    // ─── Auto-Dismiss Modals ──────────────────────────────────────
    function autoDismissModals() {
        var allButtons = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
        var gotItBtn = allButtons.find(function(b) {
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
            var propsKey = Object.keys(btn).find(function(k) { return k.startsWith("__reactProps$"); });
            if (propsKey && btn[propsKey] && typeof btn[propsKey].onClick === "function") {
                btn[propsKey].onClick({ preventDefault: function(){}, stopPropagation: function(){} });
            }
        } catch (e) {}

        // 2. React Fiber tree walk
        try {
            var fiberKey = Object.keys(btn).find(function(k) {
                return k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$");
            });
            if (fiberKey) {
                var fiber = btn[fiberKey];
                var depth = 0;
                while (fiber && depth < 20) {
                    if (fiber.memoizedProps && typeof fiber.memoizedProps.onClick === "function") {
                        fiber.memoizedProps.onClick({ preventDefault: function(){}, stopPropagation: function(){} });
                        break;
                    }
                    if (fiber.pendingProps && typeof fiber.pendingProps.onClick === "function") {
                        fiber.pendingProps.onClick({ preventDefault: function(){}, stopPropagation: function(){} });
                        break;
                    }
                    fiber = fiber.return;
                    depth++;
                }
            }
        } catch (e) {}

        // 3. Full DOM MouseEvent Cascade
        try {
            btn.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
            btn.click();
        } catch (e) {}
        return true;
    }

    // ─── Find & Click Camera Button ───────────────────────────────
    function findCameraButton() {
        var container = pageDoc.querySelector("div[class*='livestreamPlayerActions'], div[class*='vjx7qW_livestreamPlayerActions']");
        if (container) {
            var actionBtns = Array.from(container.querySelectorAll("div[class*='actionButton'], div[class*='vjx7qW_actionButton']"));
            if (actionBtns.length >= 1) {
                return actionBtns[0];
            }
        }
        var all = Array.from(pageDoc.querySelectorAll("div[class*='actionButton'], div[class*='vjx7qW_actionButton']"));
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
            badge.innerText = "⏳ Filling Form & Going Live...";
        }

        var attempts = 0;
        var maxAttempts = 35;
        var targetTitle = title || "In mijn DM ben ik stouter... 😈";

        var interval = setInterval(function() {
            attempts++;
            autoDismissModals();

            var titleInp = findTitleInput();
            var msgInp = findMessageInput();
            var goalInp = findGoalInput();

            var allButtons = Array.from(pageDoc.querySelectorAll("button, div[role='button'], div[class*='Button']"));
            var goLiveBtn = allButtons.find(function(b) {
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
                setTimeout(function() {
                    autoDismissModals();
                    fillInput(titleInp, targetTitle);
                    clickElementViaReact(goLiveBtn);
                    try { goLiveBtn.click(); } catch(e) {}
                    console.log("[F2F-OBS] 🎯 Clicked 'Go live'!");
                    if (badge) {
                        badge.style.color = "#10b981";
                        badge.innerText = "🚀 Went Live on F2F!";
                        setTimeout(function() { badge.innerText = "🟢 OBS Sync: Port " + agentPort; }, 4000);
                    }
                }, 400);
            } else if (attempts >= maxAttempts) {
                clearInterval(interval);
                console.warn("[F2F-OBS] ⚠️ Timed out searching for live form.");
                if (badge) {
                    badge.style.color = "#ef4444";
                    badge.innerText = "⚠️ Timed out finding form";
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
        var textInputs = allInputs.filter(function(i) {
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
        try { input.click(); } catch(e) {}
        try { if (input._valueTracker) input._valueTracker.setValue(""); } catch(e) {}
        try {
            var proto = input.tagName === "TEXTAREA" 
                ? (pageWindow.HTMLTextAreaElement ? pageWindow.HTMLTextAreaElement.prototype : Object.getPrototypeOf(input))
                : (pageWindow.HTMLInputElement ? pageWindow.HTMLInputElement.prototype : Object.getPrototypeOf(input));
            var descriptor = Object.getOwnPropertyDescriptor(proto, "value");
            if (descriptor && descriptor.set) descriptor.set.call(input, value); else input.value = value;
        } catch(e) { input.value = value; }
        try {
            input.dispatchEvent(new pageWindow.InputEvent("input", { bubbles: true, cancelable: true, inputType: "insertText", data: value }));
            input.dispatchEvent(new pageWindow.Event("input", { bubbles: true, cancelable: true }));
            input.dispatchEvent(new pageWindow.Event("change", { bubbles: true, cancelable: true }));
        } catch(e) {}
        return (input.value === value || input.value.length > 0);
    }

    // ─── End Live Stream Automation (Bulletproof) ─────────────────
    function executeEndStream() {
        console.log("[F2F-OBS] 🛑 Ending current livestream from Discord...");
        var exitBtn = pageDoc.querySelector("div[class*='logoutIcon'], div[class*='logout'], div[class*='vjx7qW_logoutIcon'], div[class*='exitIcon']");
        if (!exitBtn) {
            var container = pageDoc.querySelector("div[class*='livestreamPlayerActions'], div[class*='vjx7qW_livestreamPlayerActions']");
            if (container) {
                var btns = Array.from(container.querySelectorAll("div[class*='actionButton'], div[class*='logoutIcon'], div[role='button']"));
                if (btns.length >= 2) exitBtn = btns[btns.length - 1];
            }
        }
        if (exitBtn) {
            clickElementViaReact(exitBtn);
            try { exitBtn.click(); } catch(e) {}
        }
        var confirmAttempts = 0;
        var confirmInterval = setInterval(function() {
            confirmAttempts++;
            var confirmBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
            var endConfirm = confirmBtns.find(function(b) {
                var txt = (b.innerText || b.textContent || "").trim().toLowerCase();
                return txt.includes("end") || txt.includes("yes") || txt.includes("confirm") || txt.includes("beëindigen") || txt.includes("stop");
            });
            if (endConfirm && endConfirm !== exitBtn) {
                clearInterval(confirmInterval);
                clickElementViaReact(endConfirm);
                try { endConfirm.click(); } catch(e) {}
            } else if (confirmAttempts >= 10) {
                clearInterval(confirmInterval);
            }
        }, 200);

        setTimeout(function() {
            seenMessageIds.clear();
            if (liveSocket) { try { liveSocket.close(); } catch(e) {} }
            if (badge) {
                badge.style.color = "#ef4444";
                badge.innerText = "🛑 Stream Ended (Clean Reset)";
            }
            pageWindow.location.href = "https://f2f.com/live/";
        }, 1200);
    }

    // ─── Live Chat: Send & Delete ─────────────────────────────────
    function sendLiveChatMessage(text) {
        console.log("[F2F-OBS] 💬 Processing Live Chat dispatch from Discord:", text);
        if (liveSocket && liveSocket.readyState === 1) {
            var channel = activeChannelName || window.location.pathname.replace(/\//g, "") || "stream";
            try {
                liveSocket.send("42" + JSON.stringify(["livestream:chat:message:send", [channel, text]]));
                console.log("[F2F-OBS] ⚡ Sent live chat message via socket:", text);
            } catch(e) {}
        }
        var inputs = Array.from(pageDoc.querySelectorAll("textarea, input:not([type='hidden'])"));
        var chatInput = inputs.find(function(inp) {
            var ph = (inp.placeholder || inp.getAttribute("placeholder") || inp.getAttribute("aria-label") || "").toLowerCase();
            return ph.includes("say") || ph.includes("comment") || ph.includes("chat") || ph.includes("message") || ph.includes("bericht") || ph.includes("type");
        });
        if (!chatInput) {
            var textInputs = inputs.filter(function(i) { return i.type === "text" || !i.type || i.tagName === "TEXTAREA"; });
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
                    try { sendBtn.click(); } catch(e) {}
                }
            }
        }
    }

    function deleteLiveChatMessage(messageId, text, username) {
        console.log("[F2F-OBS] 🗑️ Executing delete for message:", { messageId, text, username });
        if (liveSocket && liveSocket.readyState === 1 && messageId) {
            var channel = activeChannelName || window.location.pathname.replace(/\//g, "") || "stream";
            try {
                liveSocket.send("42" + JSON.stringify(["livestream:chat:message:delete", [channel, String(messageId)]]));
                console.log("[F2F-OBS] ⚡ Dispatched message delete via socket:", messageId);
            } catch(e) {}
        }
        var chatItems = Array.from(pageDoc.querySelectorAll("div[class*='chatMessage'], div[class*='messageItem'], div[class*='ChatMessage'], div[class*='comment']"));
        for (var item of chatItems) {
            var itemText = item.innerText || item.textContent || "";
            if ((text && itemText.includes(text)) || (username && itemText.includes(username))) {
                var moreBtn = item.querySelector("button, div[role='button'], svg, div[class*='more'], div[class*='action']");
                if (moreBtn) {
                    clickElementViaReact(moreBtn);
                    setTimeout(function() {
                        var popupBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button'], div[class*='menuItem']"));
                        var deleteOption = popupBtns.find(function(b) {
                            var t = (b.innerText || b.textContent || "").toLowerCase();
                            return t.includes("delete") || t.includes("verwijder") || t.includes("remove");
                        });
                        if (deleteOption) {
                            clickElementViaReact(deleteOption);
                            console.log("[F2F-OBS] ✅ Message deleted via UI menu!");
                        }
                    }, 300);
                    return true;
                }
            }
        }
        return false;
    }

    // ─── Poll OBS Agent for Events with Auto-Port Scan ────────────
    function pollAgentEvents() {
        ensureBadge();
        GM_xmlhttpRequest({
            method: "GET",
            url: "http://127.0.0.1:" + agentPort + "/api/camera-event?t=" + Date.now(),
            timeout: 2000,
            onload: function(response) {
                try {
                    var data = JSON.parse(response.responseText);
                    if (!isConnected) {
                        isConnected = true;
                        if (badge) {
                            badge.style.color = "#10b981";
                            badge.style.borderColor = "#10b981";
                            badge.innerText = "🟢 OBS Sync: Port " + agentPort;
                        }
                        console.log("[F2F-OBS] ✅ Connected to OBS Agent on port " + agentPort + "!");
                    }

                    if (data.event_id && data.event_id !== lastProcessedEventId) {
                        lastProcessedEventId = data.event_id;
                        console.log("[F2F-OBS] 🚨 EVENT:", data.action, "event_id:", data.event_id);

                        if (data.action === "turn_camera_off") {
                            if (badge) {
                                badge.style.color = "#f59e0b";
                                badge.style.borderColor = "#f59e0b";
                                badge.innerText = "📷 Camera OFF (" + (data.pause_delay || 10) + "s)...";
                            }
                            clickCameraButton();
                        } else if (data.action === "turn_camera_on") {
                            if (badge) {
                                badge.style.color = "#10b981";
                                badge.style.borderColor = "#10b981";
                                badge.innerText = "📷 Camera ON";
                            }
                            clickCameraButton();
                            setTimeout(function() {
                                if (badge) badge.innerText = "🟢 OBS Sync: Port " + agentPort;
                            }, 3000);
                        } else if (data.action === "go_live") {
                            executeGoLive(data.title, data.message, data.tip_goal);
                        } else if (data.action === "end_stream") {
                            executeEndStream();
                        } else if (data.action === "send_chat" && data.chat_message) {
                            sendLiveChatMessage(data.chat_message);
                        } else if (data.action === "delete_chat") {
                            deleteLiveChatMessage(data.delete_message_id, data.delete_text, data.delete_username);
                        }
                    }
                } catch (e) {
                    console.error("[F2F-OBS] Poll error:", e);
                }
                setTimeout(pollAgentEvents, 300);
            },
            onerror: function() {
                if (isConnected) {
                    isConnected = false;
                }
                var nextIdx = (candidatePorts.indexOf(agentPort) + 1) % candidatePorts.length;
                agentPort = candidatePorts[nextIdx];
                if (badge) {
                    badge.style.color = "#ef4444";
                    badge.style.borderColor = "#ef4444";
                    badge.innerText = "🔴 Scanning Port " + agentPort + "...";
                }
                setTimeout(pollAgentEvents, 1000);
            },
            ontimeout: function() {
                setTimeout(pollAgentEvents, 500);
            }
        });
    }

    pollAgentEvents();
})();
