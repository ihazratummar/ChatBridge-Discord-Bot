# MASTER PLAN: F2F Live Stream Automation & OBS Studio Integration

Master architecture and 0-to-100% operational setup guide for automating F2F Live Stream Audience Switching (15s Global ↔ 5s Followers Only) and OBS Video End Auto-Pause synchronization across agency creator models.

---

## 📐 System Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   CLIENT'S LOCAL PC                                     │
│                                                                                         │
│   ┌────────────────────────┐  OBS WS v5 (ws://127.0.0.1:4455)  ┌──────────────────────┐  │
│   │    OBS Studio v28+     │ <──────────────────────────────> │    OBS Python Agent  │  │
│   │  (Media Source Output) │                                  │   (`obs_agent/`)     │  │
│   └───────────▲────────────┘                                  └──────────┬───────────┘  │
│               │                                                          │              │
│               │ Rendered inside OBS as Dock Panel                        │              │
│   ┌───────────┴────────────┐  Local API Calls / WebSockets               │              │
│   │  OBS Custom Browser    │ <───────────────────────────────────────────┘              │
│   │  Dock UI (`dock.html`) │                                                            │
│   └────────────────────────┘                                                            │
└───────────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │
                                 Secure WSS / HTTP Webhook
                              (https://vps-server-domain/api)
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   VPS REMOTE SERVER                                     │
│                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│   │                             FastAPI Application (`fastapi_server/`)             │   │
│   │                                                                                 │   │
│   │  ┌──────────────────────┐     ┌───────────────────────┐   ┌──────────────────┐  │   │
│   │  │   FastAPI Web Engine │ ──> │ F2F Live Switcher     │ ─>│ F2F API Client   │  │   │
│   │  │ (REST & WebSockets)  │     │ (15s/5s Loop & Verif) │   │ (`curl_cffi`)    │  │   │
│   │  └──────────────────────┘     └───────────────────────┘   └────────┬─────────┘  │   │
│   └────────────────────────────────────────────────────────────────────┼────────────┘   │
│                                                                        │                │
│                                           REST API (TLS Impersonation) │                │
│                                           `POST /api/livestreams/{id}/audience/`        │
│                                                                        ▼                │
│                                                               ┌──────────────────┐      │
│                                                               │  F2F Platform    │      │
│                                                               │ (Live Broadcast) │      │
│                                                               └──────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```text
ChatBridge/
├── MASTER_PLAN.md                       # Master Architecture & Operational Guide
├── obs_agent/                           # LOCAL CLIENT PC MODULE
│   └── plan.md                          # Dedicated OBS Agent & Custom Dock Specification
└── fastapi_server/                      # REMOTE VPS SERVER MODULE
    └── plan.md                          # Dedicated FastAPI & F2F Live API Specification
```

---

## 🎯 Discovered Production Endpoints (F2F Platform)

* **Audience Switcher Endpoint**:
  `POST https://f2f.com/api/livestreams/{livestreamUuid}/audience/`
* **Headers**: `Content-Type: application/json` + `impersonate-user: <creator_handle>`
* **Payload Options**:
  - `{"target": "public"}` $\rightarrow$ **Global FYP Preview (15s)**
  - `{"target": "fans-and-followers"}` $\rightarrow$ **Followers & Fans Only (5s)**
  - `{"target": "fans-only"}` $\rightarrow$ **Paid Subscribers Only**
* **Live Session Metadata Lookup**:
  `GET https://f2f.com/api/creators/{creator_handle}/`

---

## 📑 Module Overview

1. **`obs_agent/plan.md`**: Outlines local OBS WebSocket connection (`127.0.0.1:4455`), real-time media source monitor (detects 5s remaining on active video), and OBS Custom Browser Dock UI.
2. **`fastapi_server/plan.md`**: Outlines VPS FastAPI engine, `curl_cffi` 2FA TOTP authentication, 15s Global $\leftrightarrow$ 5s Followers audience loop switcher, and video end auto-pause handler.
