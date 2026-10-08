# F2F Feed Comment & Reaction Bot (FYP & Hot Page)

## Feature Overview
An automated engagement worker that scans the **For You Page (FYP)** and **Hot Page** on F2F, distributing natural, varied comments/reactions across public posts from external creators using the agency's roster of models, with strict single-model-per-post isolation, adjustable run-timer safety limits, and Discord dashboard controls.

---

## 1. Verified F2F API Reverse-Engineering & Live Testing

Through reverse-engineering the F2F React client and live testing with authenticated agency session credentials, the exact API contracts have been discovered and verified:

1. **For You Page (FYP / Explore Feed)**:
   - `GET https://f2f.com/api/explore/v2/`
   - Returns 30 posts per page with `next` cursor, containing `{ uuid, creator, media, ... }`.
2. **Hot Page Feed**:
   - `GET https://f2f.com/api/explore/v2/?type=popular-posts`
   - Returns top trending posts sorted by popularity with `next` cursor.
3. **Post Comments Discovery (Double Verification Guard)**:
   - `GET https://f2f.com/api/creators/{creator_username}/posts/{post_uuid}/comments/`
   - Returns all comments under the post, including commenter usernames, allowing real-time verification to guarantee none of our agency models have already commented.
4. **Post Comment Submission**:
   - `POST https://f2f.com/api/creators/{creator_username}/posts/{post_uuid}/comments/`
   - Headers: `impersonate-user: {model_handle}`, `x-csrftoken: {token}`, `referer: https://f2f.com/explore/`
   - Payload: `{"content": "<comment_text>"}`
5. **Agency Creators Discovery**:
   - `GET https://f2f.com/api/agency/creators/`
   - Dynamically retrieves the full list of authorized models (e.g. `@xsophiex`, `@chantalkuyt`, `@chantalkuytmistress`, `@aylen`, `@zoelynn`, `@taier`, `@mistresstaier`).

---

## 2. Core Operational Rules & Safeguards

| Rule | Requirement | Technical Guard |
| :--- | :--- | :--- |
| **1. Max 1 Model per Post** | Only ONE agency model may comment on any individual post. | **Dual-Layer Deduplication**:<br>1. **Database Tracking**: Persistent MongoDB collection `fyp_commented_posts` stores every commented `post_uuid`. If found, the post is instantly skipped.<br>2. **Live Feed Check**: Checks existing comments from `GET /api/creators/.../comments/` to ensure no model from our roster has commented manually. |
| **2. Varied Reactions & Comments** | Do not repeat identical comments under posts; keep comments natural. | **Curated Varied Reaction Pool & Spintax**:<br>- Pool of 50+ natural compliments, emojis, and short reactions.<br>- Weighted randomization with "no immediate repeat" tracking.<br>- Custom comment templates editable directly via Discord. |
| **3. Agency Self-Exclusion** | Never comment on posts created by our own roster. | Strict blacklist matching author against active agency handles (`@xsophiex`, `@chantalkuyt`, etc.). |
| **4. Adjustable Run Timer** | Bot runs for a user-specified duration (e.g., 30m, 1h, 2h) then automatically stops. | Asynchronous countdown session timer with real-time remaining-time tracking. Gracefully ends and posts a completion summary report. |
| **5. Model Rotation** | Fair distribution among models. | Round-robin rotation through active selected models so Model A, Model B, Model C take turns commenting. |
| **6. Human Pacing & Anti-Bot Detection** | Avoid triggering F2F spam or rate-limit algorithms. | Random jitter delay between comments (configurable, default: 35–65 seconds between comments). |

---

## 3. Architecture & Modular Plan

### Component 1: F2F Client Expansion (`discord_bot/services/f2f_client.py`)
- Add `get_agency_creators()` to retrieve all authorized models from `/api/agency/creators/`.
- Add `get_feed_posts(feed_type: str = "fyp", cursor: str | None = None)` supporting `"fyp"` (`/api/explore/v2/`) and `"hot"` (`/api/explore/v2/?type=popular-posts`).
- Add `get_post_comments(creator: str, post_uuid: str)` to fetch existing comments on a post.
- Add `post_comment(creator: str, post_uuid: str, model: str, content: str)` to submit a comment impersonating the chosen model.

### Component 2: FYP Automation Service (`discord_bot/services/fyp_comment_service.py`)
- **State Management**:
  - Track active running session: start time, duration, target feeds, active models, comments posted counter, posts scanned counter.
  - Background worker loop executing feed traversal and comment dispatch.
- **Deduplication Engine**:
  - Query MongoDB collection `fyp_commented_posts` before commenting on any post.
  - Save newly commented posts with `{ post_uuid, post_creator, model_used, comment_text, feed_type, timestamp }`.
- **Comment Selection & Rotation Engine**:
  - Round-robin model picker among selected active models.
  - Random non-repeating comment picker from the template pool.
- **Session Lifecycle**:
  - `start_session(models: list[str], feeds: list[str], duration_minutes: int)`
  - `stop_session()`: Cancels the running loop gracefully.
  - Real-time status reporting: returns status, elapsed time, remaining time, comment counts per model.

### Component 3: Discord UI & Slash Command Integration (`discord_bot/cogs/fyp_automation.py`)
- **Slash Commands**:
  - `/fyp_bot`: Opens the interactive **FYP & Hot Commenter Control Dashboard**.
- **Interactive UI (`F2FFYPControllerView`)**:
  - **Feed Selection**: Select `FYP (For You Page)`, `Hot Page`, or `Both Feeds`.
  - **Duration Selector**: `30 Minutes`, `1 Hour`, `2 Hours`, or `Custom`.
  - **Model Filter**: Toggle which agency models participate (or Select All).
  - **`[ 🚀 Start FYP Bot ]`**: Launches the background runner.
  - **`[ 🛑 Stop Bot ]`**: Emergency stop button to instantly halt comments.
  - **`[ 📝 View / Edit Comment Pool ]`**: Button opening modal to add/edit comment lines.
  - **Live Progress Embed**: Live status card displaying runtime, countdown timer, posts engaged, and per-model breakdown.
