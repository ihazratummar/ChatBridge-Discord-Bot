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

(function() {
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
        } catch(e) {}

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
        } catch(e) {}

        // Tier 3: Saved in this Chrome Profile's isolated localStorage
        try {
            var saved = localStorage.getItem("f2f_active_creator");
            if (saved && CREATORS[saved.toLowerCase()]) {
                return saved.toLowerCase();
            }
        } catch(e) {}

        // Tier 4: DOM Auto-detect (from pathname, title, or body text)
        try {
            var path = pageWindow.location.pathname.toLowerCase();
            for (var key in CREATORS) {
                if (path.includes(key)) {
                    localStorage.setItem("f2f_active_creator", key);
                    return key;
                }
            }
        } catch(e) {}

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

    // ─── Safe Black Shield Canvas Stream (Anti-Leak Guarantee) ─────
    var shieldStreamInstance = null;
    function getSafeShieldStream(audioTrack) {
        var canvas = pageDoc.createElement("canvas");
        canvas.width = 1280;
        canvas.height = 720;
        var ctx = canvas.getContext("2d");

        function renderFrame() {
            // Dark elegant background
            ctx.fillStyle = "#090d16";
            ctx.fillRect(0, 0, 1280, 720);

            // Red warning perimeter
            ctx.strokeStyle = "#ef4444";
            ctx.lineWidth = 8;
            ctx.strokeRect(30, 30, 1220, 660);

            // Glow effect
            ctx.shadowColor = "rgba(239, 68, 68, 0.5)";
            ctx.shadowBlur = 15;

            // Header Icon & Text
            ctx.fillStyle = "#ef4444";
            ctx.font = "bold 44px sans-serif";
            ctx.textAlign = "center";
            ctx.fillText("🛑 VIRTUAL CAMERA OFFLINE", 640, 270);
            ctx.shadowBlur = 0;

            // Creator identification
            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 30px sans-serif";
            ctx.fillText("Channel Model: " + (creatorCfg ? creatorCfg.name : activeCreator), 640, 340);

            // Awaiting specific camera
            ctx.fillStyle = "#cbd5e1";
            ctx.font = "22px sans-serif";
            ctx.fillText("Awaiting OBS Virtual Camera: [" + targetCameraName + "]", 640, 395);

            // Anti-Leak Shield Banner
            ctx.fillStyle = "#10b981";
            ctx.font = "bold 20px sans-serif";
            ctx.fillText("🔒 ANTI-CROSSOVER SHIELD ACTIVE", 640, 465);

            ctx.fillStyle = "#64748b";
            ctx.font = "15px sans-serif";
            ctx.fillText("No other creator feeds will ever display on this channel.", 640, 500);

            // Hint
            ctx.fillStyle = "#38bdf8";
            ctx.font = "italic 16px sans-serif";
            ctx.fillText("Start Virtual Camera in OBS for " + creatorCfg.name + " to go live.", 640, 560);
        }

        renderFrame();
        var timer = setInterval(renderFrame, 1000);

        var stream = canvas.captureStream(15);
        if (audioTrack) {
            stream.addTrack(audioTrack);
        }
        return stream;
    }

    // ─── Hook enumerateDevices: Strictly Cloak All Other OBS Cameras ─
    if (pageWindow.navigator && pageWindow.navigator.mediaDevices && pageWindow.navigator.mediaDevices.enumerateDevices) {
        var origEnumerateDevices = pageWindow.navigator.mediaDevices.enumerateDevices.bind(pageWindow.navigator.mediaDevices);
        pageWindow.navigator.mediaDevices.enumerateDevices = async function() {
            var devices = await origEnumerateDevices();
            var videoDevs = devices.filter(function(d) { return d.kind === "videoinput"; });
            var otherDevs = devices.filter(function(d) { return d.kind !== "videoinput"; });
            detectedVideoDevices = videoDevs;

            if (targetCameraName && videoDevs.length > 0) {
                // Find matching device
                var targetIdx = videoDevs.findIndex(function(d) {
                    if (!d.label) return false;
                    var lbl = d.label.toLowerCase();
                    if (lbl.includes(targetCameraName.toLowerCase())) return true;
                    if (creatorCfg && creatorCfg.cameraKeywords) {
                        return creatorCfg.cameraKeywords.some(function(kw) { return lbl.includes(kw); });
                    }
                    return false;
                });

                if (targetIdx !== -1) {
                    var targetDev = videoDevs[targetIdx];
                    // STRICT ISOLATION: Keep ONLY this creator's camera, strip every other OBS camera!
                    var safeVideo = [targetDev];
                    videoDevs.forEach(function(d) {
                        if (d.deviceId !== targetDev.deviceId && (!d.label || !d.label.toLowerCase().includes("obs"))) {
                            safeVideo.push(d);
                        }
                    });
                    console.log("%c[F2F-OBS] 🎯 Locked Video Device: " + targetDev.label + " (Cloaked all other OBS feeds)", "color: #10b981; font-weight: bold;");
                    return safeVideo.concat(otherDevs);
                } else {
                    // Target camera is offline! STRIP ALL OBS cameras so F2F cannot auto-pick another model!
                    console.warn("[F2F-OBS] ⚠️ Target Camera '" + targetCameraName + "' is OFFLINE! Cloaking all OBS cameras to prevent crossover.");
                    var nonObsVideo = videoDevs.filter(function(d) {
                        return d.label && !d.label.toLowerCase().includes("obs");
                    });
                    return nonObsVideo.concat(otherDevs);
                }
            }
            return devices;
        };
    }

    // ─── Hook getUserMedia: Zero-Crossover Safe Shield Engine ───────
    if (pageWindow.navigator && pageWindow.navigator.mediaDevices && pageWindow.navigator.mediaDevices.getUserMedia) {
        var origGetUserMedia = pageWindow.navigator.mediaDevices.getUserMedia.bind(pageWindow.navigator.mediaDevices);
        pageWindow.navigator.mediaDevices.getUserMedia = async function(constraints) {
            try {
                if (constraints && constraints.video) {
                    var rawDevs = await origEnumerateDevices();
                    var videoDevs = rawDevs.filter(function(d) { return d.kind === "videoinput"; });
                    detectedVideoDevices = videoDevs;

                    var targetDev = videoDevs.find(function(d) {
                        if (!d.label) return false;
                        var lbl = d.label.toLowerCase();
                        if (lbl.includes(targetCameraName.toLowerCase())) return true;
                        if (creatorCfg && creatorCfg.cameraKeywords) {
                            return creatorCfg.cameraKeywords.some(function(kw) { return lbl.includes(kw); });
                        }
                        return false;
                    });

                    if (targetDev && targetDev.deviceId) {
                        console.log("%c[F2F-OBS] 🔒 Enforcing Target Camera: " + targetDev.label + " (" + targetDev.deviceId + ")", "color: #10b981; font-weight: bold;");
                        if (typeof constraints.video === "boolean") {
                            constraints.video = { deviceId: { exact: targetDev.deviceId } };
                        } else if (typeof constraints.video === "object") {
                            constraints.video.deviceId = { exact: targetDev.deviceId };
                        }
                        return origGetUserMedia(constraints);
                    } else {
                        // 🛑 TARGET CAMERA IS OFFLINE! SERVE SAFE SHIELD STREAM TO AVOID CROSSOVER!
                        console.warn("%c[F2F-OBS] 🛑 ANTI-LEAK SHIELD: '" + targetCameraName + "' is OFFLINE! Serving Safe Black Stream.", "color: #ef4444; font-weight: bold; font-size: 14px;");
                        updateBadgeUI();

                        var audioTrack = null;
                        if (constraints.audio) {
                            try {
                                var aStream = await origGetUserMedia({ audio: constraints.audio });
                                if (aStream && aStream.getAudioTracks().length > 0) {
                                    audioTrack = aStream.getAudioTracks()[0];
                                }
                            } catch(e) {}
                        }
                        return getSafeShieldStream(audioTrack);
                    }
                }
            } catch (err) {
                console.warn("[F2F-OBS] getUserMedia hook exception:", err);
            }
            return origGetUserMedia(constraints);
        };
    }

    var liveSocket = null;
    var activeChannelName = "";
    var seenMessageIds = new Set();

    // ─── Pure WebSocket Chat Interceptor (No DOM Scraping) ────────
    function attachLiveChatListener(ws) {
        if (!ws || ws.__f2f_chat_attached) return;
        ws.__f2f_chat_attached = true;
        liveSocket = ws;
        console.log("%c[F2F-OBS] ⚡ Hooked F2F Live WebSocket Successfully!", "color: #3b82f6; font-weight: bold; font-size: 14px;");

        ws.addEventListener("message", function(event) {
            try {
                var data = event.data;
                if (typeof data !== "string") return;

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
                        var username = (userObj.username || userObj.display_name || payload.username || "Fan").trim();
                        var tipAmount = payload.amount || 0;
                        var isTip = tipAmount > 0 || (payload.type === "tip");

                        if (msgId.includes("#")) {
                            activeChannelName = msgId.split("#")[0];
                        }

                        var msgHash = msgId || (username + ":" + content);
                        if (!seenMessageIds.has(msgHash)) {
                            seenMessageIds.add(msgHash);
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
                        var tipUser = (payload.username || payload.display_name || "Fan").trim();
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
            } catch(e) {}
        });
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
                    } catch(e) {}
                    return ws;
                }
            });
        }
    } catch(e) {}

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
                detectedVideoDevices.forEach(function(d) {
                    if (d.label) {
                        optsHtml += `<option value="${d.label}">${d.label}</option>`;
                    }
                });
                optsHtml += `</optgroup>`;
            }

            optsHtml += `<optgroup label="Presets">`;
            knownPresets.forEach(function(p) {
                optsHtml += `<option value="${p}">${p}</option>`;
            });
            optsHtml += `</optgroup>`;

            camSelect.innerHTML = optsHtml;
            camSelect.value = currentVal;
        }

        // Check if target camera is currently online
        var isCameraOnline = detectedVideoDevices.some(function(d) {
            if (!d.label) return false;
            var lbl = d.label.toLowerCase();
            return lbl.includes(targetCameraName.toLowerCase()) || 
                   (creatorCfg.cameraKeywords && creatorCfg.cameraKeywords.some(function(kw) { return lbl.includes(kw); }));
        });

        if (statusSpan) {
            if (isConnected) {
                statusSpan.innerHTML = `<span style="color: #10b981;">🟢 Agent Port ${agentPort} Connected</span>`;
            } else {
                statusSpan.innerHTML = `<span style="color: #ef4444;">🔴 Agent Port ${agentPort} Offline</span>`;
            }
        }

        if (shieldSpan) {
            if (isCameraOnline) {
                shieldSpan.innerHTML = `<span style="color: #10b981; font-weight: bold;">🎥 ${targetCameraName} Online</span>`;
                badge.style.borderColor = "#10b981";
            } else {
                shieldSpan.innerHTML = `<span style="color: #ef4444; font-weight: bold;">🛑 ${targetCameraName} Offline (Shield Active)</span>`;
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
        Object.assign(badge.style, {
            position: "fixed", top: "12px", right: "12px",
            background: "rgba(15, 23, 42, 0.95)",
            backdropFilter: "blur(12px)",
            color: "#f8fafc",
            padding: "10px 16px", borderRadius: "16px",
            fontSize: "12px", zIndex: "9999999",
            border: "2px solid #10b981",
            boxShadow: "0 10px 35px rgba(0,0,0,0.8)",
            fontFamily: "system-ui, -apple-system, sans-serif",
            userSelect: "none",
            transition: "all 0.2s ease"
        });

        var html = `
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; cursor: pointer;" id="f2f-badge-header">
                <span id="f2f-badge-summary" style="font-weight: 600; font-size: 13px;">
                    🟢 <b>${creatorCfg.handle}</b> &nbsp;|&nbsp; 🎥 ${targetCameraName} &nbsp;|&nbsp; Port ${agentPort}
                </span>
                <span id="f2f-badge-toggle" style="font-size: 11px; opacity: 0.8; background: rgba(255,255,255,0.1); padding: 3px 8px; borderRadius: 8px;">⚙️ Controls</span>
            </div>
            <div id="f2f-badge-body" style="display: none; margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.15); flex-direction: column; gap: 8px;">
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

        // Header click: toggle expanded controls
        var header = pageDoc.getElementById("f2f-badge-header");
        var body = pageDoc.getElementById("f2f-badge-body");
        header.addEventListener("click", function() {
            isBadgeExpanded = !isBadgeExpanded;
            body.style.display = isBadgeExpanded ? "flex" : "none";
        });

        // Model Select change handler
        var mSel = pageDoc.getElementById("f2f-model-select");
        mSel.addEventListener("change", function(e) {
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
        cSel.addEventListener("change", function(e) {
            targetCameraName = e.target.value;
            localStorage.setItem("f2f_target_camera_" + activeCreator, targetCameraName);
            console.log("%c[F2F-OBS] 🎥 User Locked Target Camera: " + targetCameraName, "color: #10b981; font-weight: bold;");
            updateBadgeUI();
        });

        // Rescan button
        var rescanBtn = pageDoc.getElementById("f2f-btn-rescan");
        rescanBtn.addEventListener("click", async function(e) {
            e.stopPropagation();
            if (pageWindow.navigator && pageWindow.navigator.mediaDevices) {
                var devs = await origEnumerateDevices();
                detectedVideoDevices = devs.filter(function(d) { return d.kind === "videoinput"; });
                console.log("%c[F2F-OBS] 🔄 Rescanned Video Devices:", "color: #3b82f6; font-weight: bold;", detectedVideoDevices.map(function(d){ return d.label; }));
                updateBadgeUI();
            }
        });

        // Test button
        var testBtn = pageDoc.getElementById("f2f-btn-test-live");
        testBtn.addEventListener("click", function(e) {
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

    // ─── End Live Stream Automation (Bulletproof & Closes Tab) ───
    function closeCurrentTab() {
        console.log("[F2F-OBS] 🛑 Closing F2F Live tab cleanly...");
        seenMessageIds.clear();
        if (liveSocket) {
            try { liveSocket.close(); } catch(e) {}
        }
        if (badge) {
            badge.style.color = "#ef4444";
            badge.innerText = "🛑 Stream Ended — Closing Tab...";
        }

        // 1. Privileged userscript close
        try { window.close(); } catch(e) {}
        try { unsafeWindow.close(); } catch(e) {}
        try { pageWindow.close(); } catch(e) {}

        // 2. Cascade fallback: replace with about:blank and close
        setTimeout(function() {
            try { window.close(); } catch(e) {}
            try { pageWindow.location.replace("about:blank"); } catch(e) {}
            setTimeout(function() {
                try { window.close(); } catch(e) {}
                try { unsafeWindow.close(); } catch(e) {}
            }, 150);
        }, 300);
    }

    function executeEndStream() {
        console.log("[F2F-OBS] 🛑 Ending current livestream from Discord...");
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
            try { exitBtn.click(); } catch(e) {}

            var confirmAttempts = 0;
            var confirmInterval = setInterval(function() {
                confirmAttempts++;
                var confirmBtns = Array.from(pageDoc.querySelectorAll("button, div[role='button']"));
                var endConfirm = confirmBtns.find(function(b) {
                    var txt = (b.innerText || b.textContent || "").trim().toLowerCase();
                    return (txt.includes("end") || txt.includes("yes") || txt.includes("confirm") || txt.includes("beëindigen") || txt.includes("stop")) && !txt.includes("go live") && !txt.includes("live gaan");
                });
                if (endConfirm && endConfirm !== exitBtn) {
                    clearInterval(confirmInterval);
                    console.log("[F2F-OBS] 🎯 Confirming stream termination...");
                    clickElementViaReact(endConfirm);
                    try { endConfirm.click(); } catch(e) {}
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

    // ─── Poll OBS Agent for Events (Strict Port Lock, No Hopping) ──
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
                        console.log("[F2F-OBS] ✅ Connected to @" + activeCreator + " OBS Agent on port " + agentPort + "!");
                        updateBadgeUI();
                    }

                    if (data.event_id && data.event_id !== lastProcessedEventId) {
                        lastProcessedEventId = data.event_id;
                        console.log("[F2F-OBS] 🚨 EVENT:", data.action, "event_id:", data.event_id);

                        if (data.action === "turn_camera_off") {
                            if (badge) {
                                badge.style.color = "#f59e0b";
                                badge.style.borderColor = "#f59e0b";
                                var sum = pageDoc.getElementById("f2f-badge-summary");
                                if (sum) sum.innerHTML = `📷 <b>${creatorCfg.handle}</b> Camera OFF (${data.pause_delay || 10}s)...`;
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
                        }
                    }
                } catch (e) {
                    console.error("[F2F-OBS] Poll error:", e);
                }
                setTimeout(pollAgentEvents, 400);
            },
            onerror: function() {
                if (isConnected) {
                    isConnected = false;
                    console.warn("[F2F-OBS] ⚠️ Lost connection to @" + activeCreator + " OBS Agent on port " + agentPort);
                    updateBadgeUI();
                }
                setTimeout(pollAgentEvents, 1500);
            },
            ontimeout: function() {
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
