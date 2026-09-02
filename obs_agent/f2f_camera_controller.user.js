// ==UserScript==
// @name         F2F Live OBS Camera & Chat Automation
// @namespace    http://tampermonkey.net/
// @version      1.9
// @description  Full F2F Live Stream Automation: Auto Port Discovery, Go Live, End Stream, Auto Camera Loop Pause, Two-Way Live Chat Relay & Moderation
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

    console.log("%c[F2F-OBS] v1.9 Multi-Port Stream, Camera & Live Chat Active", "color: #10b981; font-weight: bold; font-size: 16px;");

    // Dynamic Port Discovery (Probes 8081, 8082, 8083, 8084, 8080)
    var agentPort = 8081;
    var isConnected = false;
    var lastProcessedEventId = 0;
    var candidatePorts = [8081, 8082, 8083, 8084, 8085, 8080];

    // ─── Badge UI ─────────────────────────────────────────────────
    let badge = null;
    function ensureBadge() {
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
        badge.innerText = "⏳ OBS Sync: Connecting (Port " + agentPort + ")...";
        badge.addEventListener("click", function() {
            console.log("[F2F-OBS] Manual test click...");
            var result = clickCameraButton();
            badge.innerText = result ? "🧪 TEST: Clicked Camera!" : "❌ Camera not found";
            setTimeout(function() { badge.innerText = "🟢 OBS Sync: Port " + agentPort; }, 2500);
        });
        pageDoc.body.appendChild(badge);
    }
    setInterval(ensureBadge, 1000);

    // ─── Helper: Set React Controlled Input Values ────────────────
    function setReactValue(input, value) {
        if (!input) return;
        input.focus();
        try {
            var proto = input.tagName === "TEXTAREA" ? pageWindow.HTMLTextAreaElement.prototype : pageWindow.HTMLInputElement.prototype;
            var descriptor = Object.getOwnPropertyDescriptor(proto, "value");
            if (descriptor && descriptor.set) {
                descriptor.set.call(input, value);
            } else {
                input.value = value;
            }
        } catch (e) {
            input.value = value;
        }
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    // ─── Click via React Fiber ────────────────────────────────────
    function clickElementViaReact(btn) {
        if (!btn) return false;
        try {
            var fiberKey = Object.keys(btn).find(function(k) {
                return k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$");
            });
            if (fiberKey) {
                var fiber = btn[fiberKey];
                var depth = 0;
                while (fiber && depth < 20) {
                    if (fiber.memoizedProps && typeof fiber.memoizedProps.onClick === "function") {
                        fiber.memoizedProps.onClick();
                        return true;
                    }
                    if (fiber.pendingProps && typeof fiber.pendingProps.onClick === "function") {
                        fiber.pendingProps.onClick();
                        return true;
                    }
                    fiber = fiber.return;
                    depth++;
                }
            }
        } catch (e) {
            console.error("[F2F-OBS] React fiber click error:", e);
        }

        try {
            var propsKey = Object.keys(btn).find(function(k) { return k.startsWith("__reactProps$"); });
            if (propsKey && btn[propsKey] && typeof btn[propsKey].onClick === "function") {
                btn[propsKey].onClick();
                return true;
            }
        } catch (e) {}

        try {
            btn.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
            btn.click();
        } catch (e) {}
        return true;
    }

    // ─── Find Camera Button ───────────────────────────────────────
    function findCameraButton() {
        var container = pageDoc.querySelector("div[class*='livestreamPlayerActions']");
        if (container) {
            var btns = container.querySelectorAll("div[class*='actionButton']");
            if (btns.length >= 1) {
                return btns[0];
            }
        }
        var all = pageDoc.querySelectorAll("div[class*='actionButton']");
        if (all.length >= 1) {
            return all[0];
        }
        return null;
    }

    function clickCameraButton() {
        var btn = findCameraButton();
        if (!btn) return false;
        return clickElementViaReact(btn);
    }

    // ─── Start Live Stream Automation (Go Live) ───────────────────
    function executeGoLive(title, message, tipGoal) {
        console.log("[F2F-OBS] 🚀 Executing 'Go Live' from Discord with retry loop:", { title, message, tipGoal });

        var attempts = 0;
        var maxAttempts = 30;

        var interval = setInterval(function() {
            attempts++;

            // 1. Fill Title
            var allInputs = Array.from(pageDoc.querySelectorAll("input[type='text'], input:not([type])"));
            var titleInput = allInputs.find(function(inp) {
                var ph = (inp.placeholder || "").toLowerCase();
                return ph.includes("title") || ph.includes("titel") || ph.includes("live");
            });
            if (!titleInput && allInputs.length > 0) {
                titleInput = allInputs[allInputs.length - 1];
            }
            if (titleInput && title) {
                setReactValue(titleInput, title);
            }

            // 2. Fill Message
            var msgInput = pageDoc.querySelector("textarea");
            if (msgInput && message) {
                setReactValue(msgInput, message);
            }

            // 3. Fill Tip Goal
            if (tipGoal) {
                var goalInput = allInputs.find(function(inp) {
                    var ph = (inp.placeholder || "").toLowerCase();
                    return ph.includes("goal") || ph.includes("doel") || ph.includes("set");
                });
                if (goalInput) {
                    setReactValue(goalInput, tipGoal);
                }
            }

            // 4. Find and click "Go live" button
            var allButtons = Array.from(pageDoc.querySelectorAll("button, div[role='button'], div[class*='Button']"));
            var goLiveBtn = allButtons.find(function(b) {
                var txt = (b.innerText || b.textContent || "").toLowerCase();
                return txt.includes("go live") || txt.includes("live gaan");
            });

            if (goLiveBtn) {
                clearInterval(interval);
                console.log("[F2F-OBS] ✅ Found 'Go live' button on attempt #" + attempts + "! Clicking now...");
                clickElementViaReact(goLiveBtn);
                if (badge) {
                    badge.style.color = "#10b981";
                    badge.innerText = "🚀 Went Live on F2F!";
                    setTimeout(function() { badge.innerText = "🟢 OBS Sync: Port " + agentPort; }, 4000);
                }
            } else if (attempts >= maxAttempts) {
                clearInterval(interval);
                console.warn("[F2F-OBS] 'Go live' button did not appear within 15s.");
            }
        }, 500);
    }

    // ─── End Live Stream Automation ───────────────────────────────
    function executeEndStream() {
        console.log("[F2F-OBS] 🛑 Ending current livestream from Discord...");
        var container = pageDoc.querySelector("div[class*='livestreamPlayerActions']");
        var exitBtn = null;
        if (container) {
            var btns = container.querySelectorAll("div[class*='actionButton'], div[role='button']");
            if (btns.length >= 4) exitBtn = btns[3];
        }
        if (!exitBtn) {
            exitBtn = pageDoc.querySelector("div[class*='logoutIcon'], div[class*='exitIcon']");
        }

        if (exitBtn) {
            clickElementViaReact(exitBtn);
            setTimeout(function() {
                var confirmBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
                var endConfirm = confirmBtns.find(function(b) {
                    var txt = (b.innerText || b.textContent || "").toLowerCase();
                    return txt.includes("end") || txt.includes("yes") || txt.includes("confirm") || txt.includes("beëindigen");
                });
                if (endConfirm) {
                    clickElementViaReact(endConfirm);
                }
            }, 600);
            if (badge) {
                badge.style.color = "#ef4444";
                badge.innerText = "🛑 Stream Ended";
            }
        }
    }

    // ─── Live Chat: Send Message (Discord -> F2F) ─────────────────
    function sendLiveChatMessage(text) {
        var input = pageDoc.querySelector("input[placeholder*='Chat'], textarea[placeholder*='Chat'], input[class*='chatInput'], textarea[class*='chatInput']");
        if (!input) {
            input = pageDoc.querySelector("input[type='text']");
        }
        if (input) {
            setReactValue(input, text);
            input.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13 }));
            input.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: "Enter", code: "Enter", keyCode: 13 }));

            var sendBtn = pageDoc.querySelector("button[type='submit'], div[class*='sendButton'], svg[class*='sendIcon']");
            if (sendBtn) {
                sendBtn.click();
            }
            console.log("[F2F-OBS] ✅ Live Chat message submitted to F2F Live!");
        }
    }

    // ─── Live Chat: Delete Message (Discord -> F2F) ───────────────
    function deleteLiveChatMessage(messageId, text, username) {
        console.log("[F2F-OBS] 🗑️ Executing delete for message:", { messageId, text, username });
        var chatItems = Array.from(pageDoc.querySelectorAll("div[class*='chatMessage'], div[class*='messageItem'], div[class*='ChatMessage']"));
        for (var item of chatItems) {
            var itemText = item.innerText || item.textContent || "";
            if ((text && itemText.includes(text)) || (username && itemText.includes(username))) {
                var moreBtn = item.querySelector("button, div[role='button'], svg");
                if (moreBtn) {
                    clickElementViaReact(moreBtn);
                    setTimeout(function() {
                        var popupBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button'], div[class*='menuItem']"));
                        var deleteOption = popupBtns.find(function(b) {
                            var t = (b.innerText || b.textContent || "").toLowerCase();
                            return t.includes("delete") || t.includes("verwijder");
                        });
                        if (deleteOption) {
                            clickElementViaReact(deleteOption);
                            console.log("[F2F-OBS] ✅ Message deleted successfully!");
                        }
                    }, 300);
                    return true;
                }
            }
        }
        return false;
    }

    // ─── Live Chat: Observe Incoming Messages (F2F -> Discord) ─────
    var seenMessageIds = new Set();

    function initLiveChatObserver() {
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) {
                        var isChat = node.className && typeof node.className === "string" && (node.className.includes("chatMessage") || node.className.includes("messageItem"));
                        var chatElem = isChat ? node : node.querySelector("div[class*='chatMessage'], div[class*='messageItem']");

                        if (chatElem) {
                            var textContent = chatElem.innerText || chatElem.textContent || "";
                            var msgHash = textContent.trim();
                            if (msgHash && !seenMessageIds.has(msgHash)) {
                                seenMessageIds.add(msgHash);

                                var userSpan = chatElem.querySelector("span[class*='username'], strong, a");
                                var username = userSpan ? userSpan.innerText.trim() : "Viewer";
                                var messageText = textContent.replace(username, "").trim();

                                console.log("[F2F-OBS] 💬 Intercepted Live Chat:", username, "->", messageText);

                                GM_xmlhttpRequest({
                                    method: "POST",
                                    url: "http://127.0.0.1:" + agentPort + "/api/incoming-chat",
                                    headers: { "Content-Type": "application/json" },
                                    data: JSON.stringify({
                                        username: username,
                                        text: messageText,
                                        type: messageText.includes("€") || messageText.includes("tip") ? "tip" : "chat"
                                    })
                                });
                            }
                        }
                    }
                });
            });
        });

        observer.observe(pageDoc.body, { childList: true, subtree: true });
        console.log("[F2F-OBS] 👁️ Live Chat Observer active!");
    }

    setTimeout(initLiveChatObserver, 2000);

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
                // Try scanning next candidate port if not connected
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
