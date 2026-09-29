# Reference — Per-channel activity, snapshot vs period, creative retrieval, channels

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

## Per-channel activity & typology (robust, Reports-only)
Because push is enumerable but email/SMS are **not listable** from Reports, per-channel
robustness comes from combining three endpoints. Use `scripts/channel_activity.py`.

**1. Detect every active channel from `/api/reports/sends` (per-channel daily), not `/devices`.**
`/sends` returns per-day columns `ios`, `android`, `amazon`, `web`, `email`, `sms`. A channel
is **active** if its period volume > 0 — even when `/devices` shows `opted_in: 0`. This is a
real, verified trap: e.g. a project can show `email opted_in: 0` in the snapshot while sending
tens of millions of emails in the period. `channel_summary(...)` sets
`email_active_but_zero_optin: true` for exactly this case. Never declare a channel inactive
from the `/devices` snapshot alone.

**2. Email funnel from Airship standard events** (`email_funnel_from_events(events)`).
Email engagement surfaces in `/api/reports/events` as standard events with `location: custom`:

| Event name | Funnel stage |
|---|---|
| `injection` | injected (accepted by Airship) |
| `delivery` | delivered (accepted by receiving MTA) |
| `initial_open` | unique opens |
| `open` | opens (incl. repeats) |
| `click` | clicks |
| `bounce` | bounces |
| `spam_complaint` | spam complaints |
| `unsubscribe` | unsubscribes |
| `open_tracking_opt_out` | open-tracking opt-outs |

From these: delivery rate = delivered/injected; open rate = unique_opens/delivered; CTR =
clicks/delivered; CTOR = clicks/unique_opens; bounce/spam/unsubscribe rates. This is the
**robust email KPI set** the Reports API supports without a message list. Position vs the
`[Internal baseline]` (no external email benchmark). SMS, when present, is measured from
`/sends` volume (+ any SMS events); per-message needs supplied IDs.

**Email has TWO volume counters and they disagree — reconcile them (gate-enforced).**
`/api/reports/sends` counts email sends over the window; `injection`/`delivery` above come
from the event feed. On a real account the feed injects ~11% more than `/sends` reports for
the same window. A review that put one figure in the executive summary and the other in the
funnel published **more email delivered than sent**, and its headline 52.8% open rate stood
on the funnel's base without saying so — so the rate depended on whichever counter was
wrong. Call `channel_activity.email_reconcile(reports_sends, funnel)` and render
`ri.email_reconcile_note(rec, lang)` in §14 whenever email is active. The rules the note
states are the rules to follow: **volume KPIs use `/api/reports/sends`**, the **open rate
denominator is `delivered`**, and the two counters are never added, averaged, or presented
as one figure. Check `funnel_internally_consistent` too — when injected less bounced does
not return delivered, the feed itself is unreliable and every email rate is provisional.

**3. Automated-vs-one-shot typology PER CHANNEL.**
- **Push** — per campaign, High confidence: `classify_campaigns.classify()` on the merged
  activity-log + responses/list inventory (group_id + normalized message_name + cadence).
- **Email / SMS** — channel-level, Low/Medium confidence when no message list:
  `channel_activity.daily_cadence(daily_series)` classifies the channel's daily send series
  (near-daily continuous ⇒ automated program; sparse spikes ⇒ one-shot heavy). Upgrade to
  per-message typology (group ⇒ automated, single push ⇒ one-shot) when the user supplies
  email/SMS `push_id`/`group_id`.

Every active channel gets its own analysis block: **volume + engagement (funnel/rates) +
typology** — never a bare volume number, never blended with another channel.
## Scope of measurement — snapshot (whole base) vs period
Keep these two families of metrics **strictly separate** in analysis and in the report;
never mix a snapshot figure with a period figure in the same KPI.
- **Snapshot / whole base** = `/api/reports/devices` **only**. Point-in-time state of the
  entire installed base at `date_closed`: `unique_devices`, `opted_in`, `opted_out`,
  `uninstalled` per platform. This is the **only** source for the **opt-in rate** and
  installed-base size. Tag these "(snapshot DD/MM)".
- **Period** = `sends`, `opens`, `optins`, `optouts`, `events`, `responses/list`,
  `activity/details`, per-push/per-group reports — all bounded by the analysis window. `optins`/`optouts`
  are **event flows during the period**, NOT a net change of the installed base, and they
  do **not** equal the snapshot `opted_in`/`opted_out` counts. Tag these "(period)".
- A period opt-in/opt-out **event** balance (sum optins − sum optouts) describes activity
  flow only; it must never be presented as "the base grew/shrank by X".
- **Every count tile in the executive summary states which kind it is (gate-enforced).**
  `(période)` / `(period)` / `(events)` for a flow, `(instantané)` / `(snapshot)` for a
  point-in-time base. The doctrine above existed and a delivered summary still put
  "Opt-ins app 1.7M" three tiles above "Opt-outs 2.6M" — read straight down, a
  collapsing base; in fact a snapshot next to thirty days of events. The classification
  lives in `build_facts.KPI_TEMPORAL` and the canonical labels already carry the marker,
  so a tile built from `F["kpis"]` inherits it. Rates are deliberately exempt: nobody
  reads "direct open rate 24%" as a headcount, and tagging them would only add noise.

**Web opt-in and app opt-in are not on the same scale — do not compare them.** Both come
out of `/devices` as a clean `opted_in / unique_devices`, which is exactly what makes the
comparison tempting and wrong. They measure different acts. A browser permission prompt is
fired by the site at a moment it chooses, on a visitor who may never return, and it is
reversed in one click from the address bar; an iOS or Android system prompt is asked once
per install, is costly to reverse, and the denominator is an installed base the user chose
to keep. A web rate near 75% against an app rate near 47% therefore says the two prompts
are different, not that the web audience is more willing. The same applies to anything
built on those bases — messages per opted-in browser against messages per opted-in device
is not a pressure comparison, and reporting it as a ratio ("45× less solicited") is a
finding the client will reject on sight. Report each channel on its own scale, benchmark
each against its own vertical band, and when the contrast looks striking, make the reason
they do not meet the point rather than the ratio.

### Creative retrieval — which source by send type
Determine each top campaign's `push_type` from `responses/list`, then pick the source:

| Send type | Has per-push body? | Where the creative lives (Reports only) |
|---|---|---|
| **BROADCAST / SEGMENTS / A-B** (mass) | ✅ Usually | `GET /api/reports/perpush/pushbody/{push_id}` → notif text + Message Center / email HTML when embedded in the push payload. |
| **UNICAST / Create-and-Send** (1:1, automation/journey) | ❌ Usually empty | No Content API in this skill. Call `pushbody` anyway for **`options.message_name`**, `campaigns.categories`, and any partial metadata. If no HTML/notif content → **illustrative reconstruction** (labelled). |

Rules of thumb:
- Always try `perpush/pushbody` for analysed top messages — even UNICAST may expose metadata.
- **Do not call** `/api/content/templates` or any `/api/content/*` endpoint.
- Render real HTML from pushbody with `scripts/render_email.py`. Reconstruct with
  `scripts/render_mocks.py` **only** when pushbody has no usable creative content.
  `render_email.py` pre-downloads the email's remote CDN images (Airship emails are
  image-based) to local `file://` before rendering, renders headless at scale 1, **kills
  the whole Chrome process group** (leaked headless children are the #1 cause of blank
  renders), and retries a blank frame. If you render email HTML yourself, do the same.

#### Push hero image (rich push) — download it and preview WITH the image
Rich/expanded pushes carry a hero image. In the decoded `perpush/pushbody`, the image URL
sits at:
- iOS: `notification.ios.media_attachment.url` (sometimes under `content[].url`);
- Android: `notification.android.style.big_picture` (or `notification.android.big_picture`).

Do **not** ship a text-only mock when an image exists. Instead:
```python
from render_mocks import fetch_media, render_push
img = fetch_media(image_url, "creatives/hero.jpg")     # None if the download fails
# 5-tuple → renders WITH the real image; 4-tuple → text-only card (fallback)
render_push([(time, title, body, tag, img)], "creatives/push.png", app_name="<App>")
```
`fetch_media` is a plain binary GET (public CDN URL, no auth). If it returns None (or no URL
is present), fall back to the 4-tuple text-only card and label it a reconstruction. The
same push can carry both an iOS `media_attachment` and an Android `big_picture` — either is
enough to treat the push as rich.

#### Message Center / full-screen mobile templates — phone-sized preview only
MC and inbox full-screen templates render as **very tall PNGs** (2000+ px — the full
scrollable page). Never embed them as a bare `<img>` in the report: they overflow mobile
screens and dominate the creatives page.

**At render time** (`render_email.py`):
```python
render_email(html_body, "creatives/mc.png", width=375, max_height=720)
```
`width=375` matches a phone viewport; `max_height=720` keeps only above-the-fold content
(after autocrop).

**In the HTML report** (`report_interactive.py`):
```python
creative_mc_preview(datauri("creatives/mc.png"), "Message Center · …")
```
Wraps the image in `.ir-mc-viewport` (~380–420 px tall, rounded phone frame) with
`object-fit:cover; object-position:top` so any remaining tail is clipped. Use
`creative_push_preview(...)` for push lock-screen cards (natural height).

#### Real app logo — resolve once, reuse in every push preview
For realistic previews, render the notification icon as the **real app logo**, not a colored
tile. Resolve it once during brand research (step 1) and pass it to every `render_push`:
```python
from render_mocks import fetch_app_icon
icon = fetch_app_icon("<App/brand name>", "creatives/app_icon.png", country="fr")  # or "us"
render_push([...], "creatives/push.png", app_name="<App>", app_icon=icon)  # icon=None → tile
```
- **Source order**: (1) iTunes Search API (`itunes.apple.com/search?term=<brand>&entity=software`)
  → `artworkUrl512`/`artworkUrl100` for the iOS App Store icon; (2) Google Play store-page
  `og:image` **only when `query` is an Android package id** (e.g. `com.example.app`) — Play
  *search* is skipped because its og:image is a generic Play logo. Uses a curl fallback (the
  macOS system Python often fails TLS verification, same as `fetch_media`).
- **Override**: if auto-resolution picks the wrong app (common name collisions) or returns
  None, the user can supply the exact **App Store name / country** or the **Android package
  id**; pass that as `query`. Document which source produced the logo.
- If no logo is found, `render_push` keeps the colored accent tile — acceptable fallback,
  but prefer the real logo whenever it resolves.
## Channels
- A channel is **present** only if devices/sends > 0. State absent channels (often
  Email/SMS/Web) explicitly; do not create empty pages.
- Web push devices that are all opted-out = channel not activated.
- **Email/SMS presence must be judged from two sources together**: the email/SMS
  `opted_in` count in `/reports/devices` AND the top-level `sends` in `perpush/detail`
  (or `pergroup/detail`) for that message — **not** from `responses/list`/activity log,
  which does not reliably surface email/SMS. Only call the channel "absent"/"inactive"
  when both sources agree (see "Email / SMS performance" above).
