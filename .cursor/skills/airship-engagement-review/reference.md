# Reference — endpoints, definitions, branding

## Airship Reports API endpoints
Call via MCP `call_airship_api` with `{method, path, params}`.

| Data | Path | Params | Definition |
|---|---|---|---|
| Sends | `/api/reports/sends` | start, end, precision=DAILY | Notifications sent per platform (ios/android/sms/email/web). |
| Opens | `/api/reports/opens` | start, end, precision=DAILY | App/notification opens as counted by Airship (influenced included). |
| Opt-ins | `/api/reports/optins` | start, end, precision=DAILY | Daily opt-in **events** (not net base; includes re-detections/reinstalls). |
| Opt-outs | `/api/reports/optouts` | start, end, precision=DAILY | Daily opt-out **events**. |
| Devices | `/api/reports/devices` | — | Snapshot: unique devices, opted_in / opted_out / uninstalled per platform → **opt-in rate** (authoritative). |
| Responses | `/api/reports/responses/list` | start, end, limit, (next_page cursor) | Push list: `push_type` (BROADCAST/SEGMENTS/UNICAST/A-B), `sends`, `direct_responses`, `group_id`. |
| Per-push | `/api/reports/perpush/detail/{push_id}` | — | Sends/direct/influenced per push. |
| Push body | `/api/reports/perpush/pushbody` | push_id | Base64 creative (notif + Message Center/Email HTML). **404 on some projects.** |
| Events | `/api/reports/events` | start, end, precision=MONTHLY, page_size, page | name, location, conversion, count, value. **Paginate all pages.** |
| Activity | `/api/reports/activity/details` | — | Extra granularity if accessible. |

Dates accepted as `YYYY-MM-DD`. To page `responses/list`, follow `next_page`
(`push_id_start` + `resume_at_time`). A too-narrow window returns only the latest
(small) sends; target peak-send days to find broadcasts.

## Definitions
- **Direct**: action after a direct open of the push.
- **Indirect (influenced)**: action after push received without a direct open, within
  the attribution window.
- **Unattributed**: action with no associated push.
- **Push-attributed** = direct + indirect.
- **Opt-in rate** = opted_in / unique devices (devices snapshot).
- **Opt-in/opt-out events**: daily permission state changes; not net base change.
- **Event `value`**: client-declared counter/weight, **not currency** — never convert to money.
- **Push pressure** (indicator): sends / weeks / opted-in base.
- **`location` values**: `custom` (app behaviour), `in_app_message` (fullscreen),
  `in_app_pager` (carousels/stories), `ua_mcrap` (Message Center), `ua_interactive_notification`
  (notification buttons).

## Channels
- A channel is **present** only if devices/sends > 0. State absent channels (often
  Email/SMS/Web) explicitly; do not create empty pages.
- Web push devices that are all opted-out = channel not activated.

## Airship branding (visual)
Confirm against airship.com if possible.
- Ink / dark bg: `#16161D`; text `#1A1A2E`; grey `#6A6A82`.
- Primary accent (red/coral): `#E7233E`.
- Secondary: indigo `#3D2CE0`, blue `#2A5BD7`.
- Positive/tertiary: mint `#12B886`.
- Light neutral / panels: `#F5F5F7`; hairline `#E5E5EC`.
- Sans-serif, generous whitespace, bold titles, big-number KPIs.
- Footer: "Powered by Airship" + "Confidential document".
- Origin tags: `[Data]`, `[Brand context]`, `[Data+Context]` (localize labels per report language).

## Page / PDF rules
- HTML: `@page{size:1240px 1754px;margin:0}` + `.page{width:1240px;height:1754px}`.
- PDF: Chrome `--headless=new --print-to-pdf --no-pdf-header-footer`.
- PNG: PyMuPDF render at 2x, stitch pages vertically.
- Verify final PDF page count equals the number of `.page` divs (no overflow).
