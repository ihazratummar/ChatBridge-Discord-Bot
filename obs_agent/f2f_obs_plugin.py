"""
F2F Live Stream OBS Native Plugin Script
Runs directly inside OBS Studio (Tools -> Scripts).
Monitors active video media source duration and alerts FastAPI when video is ending.
"""

import obspython as obs
import urllib.request
import urllib.parse
import json
import threading
import time

# --- Global State & Settings ---
selected_creator = "xsophiex"
vps_server_url = "http://127.0.0.1:8000"
pause_trigger_seconds = 5.0
media_source_name = ""
last_trigger_time = 0
last_telemetry_time = 0

CREATORS = [
    "xsophiex",
    "chantalkuyt",
    "aylen"
]

def script_description():
    return (
        "<h2>🎬 F2F Live Manager (Native OBS Plugin)</h2>"
        "<p>Automatically monitors active video playback inside OBS and alerts your FastAPI backend "
        "when <b>5 seconds remain</b> on the video loop.</p>"
        "<hr>"
    )

def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "creator", "xsophiex")
    obs.obs_data_set_default_string(settings, "vps_url", "http://127.0.0.1:8000")
    obs.obs_data_set_default_double(settings, "trigger_sec", 5.0)
    obs.obs_data_set_default_string(settings, "media_source", "")

def script_properties():
    props = obs.obs_properties_create()

    # 1. Creator Model Dropdown
    p_creator = obs.obs_properties_add_list(
        props,
        "creator",
        "👤 Active Creator Model",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING
    )
    for c in CREATORS:
        obs.obs_property_list_add_string(p_creator, f"@{c}", c)

    # 2. Specific Media Source (optional, auto-detects if empty)
    p_sources = obs.obs_properties_add_list(
        props,
        "media_source",
        "🎥 Target Media Source",
        obs.OBS_COMBO_TYPE_LIST,
        obs.OBS_COMBO_FORMAT_STRING
    )
    obs.obs_property_list_add_string(p_sources, "[ Auto-Detect Any Media Source ]", "")
    
    # Populate existing media sources in OBS
    sources = obs.obs_enum_sources()
    if sources:
        for source in sources:
            s_id = obs.obs_source_get_unversioned_id(source)
            if s_id in ("ffmpeg_source", "vlc_source", "media_source", "image_source") or "media" in s_id or "ffmpeg" in s_id:
                name = obs.obs_source_get_name(source)
                obs.obs_property_list_add_string(p_sources, name, name)
        obs.source_list_release(sources)

    # 3. Trigger Threshold Slider
    obs.obs_properties_add_float_slider(
        props,
        "trigger_sec",
        "⏱️ Alert When (Seconds Left)",
        1.0,
        15.0,
        0.5
    )

    # 4. FastAPI Server URL
    obs.obs_properties_add_text(
        props,
        "vps_url",
        "🌐 FastAPI VPS Server URL",
        obs.OBS_TEXT_DEFAULT
    )

    # 5. Test Button
    obs.obs_properties_add_button(
        props,
        "test_button",
        "🧪 Send Test Webhook to FastAPI",
        test_webhook_clicked
    )

    return props

def script_update(settings):
    global selected_creator, vps_server_url, pause_trigger_seconds, media_source_name
    selected_creator = obs.obs_data_get_string(settings, "creator") or "xsophiex"
    vps_server_url = (obs.obs_data_get_string(settings, "vps_url") or "http://127.0.0.1:8000").rstrip("/")
    pause_trigger_seconds = obs.obs_data_get_double(settings, "trigger_sec") or 5.0
    media_source_name = obs.obs_data_get_string(settings, "media_source")
    print(f"✅ [F2F Plugin] Settings Updated: Creator=@{selected_creator}, Trigger={pause_trigger_seconds}s, VPS={vps_server_url}, Source='{media_source_name or 'AUTO'}'")

def send_webhook_async(endpoint, payload):
    def worker():
        try:
            url = f"{vps_server_url}{endpoint}"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json", "User-Agent": "OBS-Native-Plugin/1.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if endpoint == "/api/obs-event":
                    print(f"📡 [F2F Plugin] Event Webhook Sent successfully -> HTTP {resp.status}")
        except Exception as e:
            if endpoint == "/api/obs-event":
                print(f"❌ [F2F Plugin] Failed to send webhook to {vps_server_url}{endpoint}: {e}")

    threading.Thread(target=worker, daemon=True).start()

def test_webhook_clicked(props, prop):
    print(f"🧪 [F2F Plugin] Sending test ping to {vps_server_url} for @{selected_creator}...")
    payload = {
        "event": "test_ping",
        "creator": selected_creator,
        "remaining_sec": 5.0,
        "media_name": "manual_test_ping"
    }
    send_webhook_async("/api/obs-event", payload)
    return True

def check_playback_tick():
    global last_trigger_time, last_telemetry_time
    source = None
    is_lookup = False

    if media_source_name:
        source = obs.obs_get_source_by_name(media_source_name)
        is_lookup = True
    else:
        sources = obs.obs_enum_sources()
        if sources:
            for s in sources:
                if obs.obs_source_media_get_duration(s) > 0:
                    source = s
                    break

    if not source:
        return

    try:
        duration_ms = obs.obs_source_media_get_duration(source)
        time_ms = obs.obs_source_media_get_time(source)
        state = obs.obs_source_media_get_state(source)

        if duration_ms > 0:
            remaining_sec = max(0.0, (duration_ms - time_ms) / 1000.0)
            now = time.time()
            s_name = obs.obs_source_get_name(source)

            # 1. Real-Time Telemetry Sync (Every 500ms for the Custom Dock)
            if (now - last_telemetry_time) >= 0.5:
                last_telemetry_time = now
                telemetry_payload = {
                    "creator": selected_creator,
                    "media_name": s_name,
                    "duration_sec": round(duration_ms / 1000.0, 2),
                    "remaining_sec": round(remaining_sec, 2),
                    "state": "PLAYING" if state == obs.OBS_MEDIA_STATE_PLAYING else "PAUSED"
                }
                send_webhook_async("/api/obs-telemetry", telemetry_payload)

            # 2. Trigger Video End Alert when remaining <= pause_trigger_seconds
            if state == obs.OBS_MEDIA_STATE_PLAYING and 0 < remaining_sec <= pause_trigger_seconds:
                if (now - last_trigger_time) > (pause_trigger_seconds + 3):
                    last_trigger_time = now
                    print(f"🚨 [F2F Plugin] Video ending in {remaining_sec:.1f}s on '{s_name}'! Alerting FastAPI for @{selected_creator}...")
                    
                    payload = {
                        "event": "video_ending",
                        "creator": selected_creator,
                        "remaining_sec": round(remaining_sec, 2),
                        "media_name": s_name
                    }
                    send_webhook_async("/api/obs-event", payload)
    finally:
        if is_lookup and source:
            obs.obs_source_release(source)

def script_load(settings):
    print("🚀 [F2F Plugin] Script Loaded natively in OBS Studio.")
    # Check playback every 250ms
    obs.timer_add(check_playback_tick, 250)

def script_unload():
    obs.timer_remove(check_playback_tick)
    print("🛑 [F2F Plugin] Script Unloaded from OBS Studio.")
