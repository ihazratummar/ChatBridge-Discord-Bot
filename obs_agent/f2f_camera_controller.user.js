// ==UserScript==
// @name         F2F Live OBS Camera Automation
// @namespace    http://tampermonkey.net/
// @version      1.5
// @description  Clicks the Camera button via React internals on F2F Live
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

    console.log("%c[F2F-OBS] v1.5 Camera Automation Started", "color: #10b981; font-weight: bold; font-size: 16px;");

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
        badge.innerText = "⏳ OBS Sync: Connecting...";
        badge.addEventListener("click", function() {
            console.log("[F2F-OBS] Manual test click...");
            var result = clickCameraButton();
            badge.innerText = result ? "🧪 TEST: Clicked!" : "❌ Button not found";
            setTimeout(function() { badge.innerText = "🟢 OBS Sync: Active"; }, 2500);
        });
        pageDoc.body.appendChild(badge);
    }
    setInterval(ensureBadge, 1000);

    // ─── Find Camera Button (Button #1 in action bar) ─────────────
    function findCameraButton() {
        var container = pageDoc.querySelector("div[class*='livestreamPlayerActions']");
        if (container) {
            var btns = container.querySelectorAll("div[class*='actionButton']");
            if (btns.length >= 1) {
                console.log("[F2F-OBS] Found camera button #1 in playerActions:", btns[0].className);
                return btns[0];
            }
        }
        var all = pageDoc.querySelectorAll("div[class*='actionButton']");
        if (all.length >= 1) {
            console.log("[F2F-OBS] Found camera button via fallback:", all[0].className);
            return all[0];
        }
        console.warn("[F2F-OBS] No camera button found!");
        return null;
    }

    // ─── Click via React Fiber (most reliable) ────────────────────
    function clickCameraButton() {
        var btn = findCameraButton();
        if (!btn) return false;

        // Method 1: Walk React fiber tree for onClick handler
        try {
            var fiberKey = Object.keys(btn).find(function(k) {
                return k.startsWith("__reactFiber$") || k.startsWith("__reactInternalInstance$");
            });
            if (fiberKey) {
                var fiber = btn[fiberKey];
                var depth = 0;
                while (fiber && depth < 20) {
                    if (fiber.memoizedProps && typeof fiber.memoizedProps.onClick === "function") {
                        console.log("[F2F-OBS] ✅ Found React onClick on fiber at depth " + depth + ", invoking!");
                        fiber.memoizedProps.onClick();
                        return true;
                    }
                    if (fiber.pendingProps && typeof fiber.pendingProps.onClick === "function") {
                        console.log("[F2F-OBS] ✅ Found React onClick on pendingProps at depth " + depth + ", invoking!");
                        fiber.pendingProps.onClick();
                        return true;
                    }
                    fiber = fiber.return;
                    depth++;
                }
                console.warn("[F2F-OBS] React fiber found but no onClick in tree (searched " + depth + " levels)");
            } else {
                console.warn("[F2F-OBS] No __reactFiber$ key found on element");
            }
        } catch (e) {
            console.error("[F2F-OBS] React fiber error:", e);
        }

        // Method 2: __reactProps$ direct access
        try {
            var propsKey = Object.keys(btn).find(function(k) {
                return k.startsWith("__reactProps$");
            });
            if (propsKey && btn[propsKey] && typeof btn[propsKey].onClick === "function") {
                console.log("[F2F-OBS] ✅ Found __reactProps$ onClick, invoking!");
                btn[propsKey].onClick();
                return true;
            }
        } catch (e) {
            console.error("[F2F-OBS] __reactProps$ error:", e);
        }

        // Method 3: Native events (NO view: window — that crashes in Tampermonkey sandbox)
        console.log("[F2F-OBS] Falling back to native DOM events...");
        try {
            btn.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
            btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
            btn.click();
        } catch (e) {
            console.error("[F2F-OBS] Native event error:", e);
        }

        return true;
    }

    // ─── Poll OBS Agent ───────────────────────────────────────────
    var lastProcessedEventId = 0;
    var isConnected = false;

    function pollAgentEvents() {
        ensureBadge();
        GM_xmlhttpRequest({
            method: "GET",
            url: "http://127.0.0.1:8080/api/camera-event?t=" + Date.now(),
            timeout: 2000,
            onload: function(response) {
                try {
                    var data = JSON.parse(response.responseText);
                    if (!isConnected) {
                        isConnected = true;
                        if (badge) {
                            badge.style.color = "#10b981";
                            badge.style.borderColor = "#10b981";
                            badge.innerText = "🟢 OBS Sync: Active";
                        }
                        console.log("[F2F-OBS] ✅ Connected to OBS Agent!");
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
                                if (badge) badge.innerText = "🟢 OBS Sync: Active";
                            }, 3000);
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
                    if (badge) {
                        badge.style.color = "#ef4444";
                        badge.style.borderColor = "#ef4444";
                        badge.innerText = "🔴 OBS Offline";
                    }
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
