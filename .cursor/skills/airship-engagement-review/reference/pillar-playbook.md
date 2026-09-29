# Reference — Campaign purpose, pillars and the consultative playbook

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

## Campaign purpose & pillar playbook (the consultative strategy layer)
On top of the one-shot/automated typology, map every campaign to *what it is for*. This
powers the visual strategy views (maturity matrix, coverage grid, recommendations) and is
implemented by `scripts/campaign_purpose.py` + `campaign_playbook.json`, fed by the canonical
`scripts/campaign_inventory.py`. **Reports API only** — the content used for detection comes
from decoded `perpush/pushbody`, never the Content API.

**Scope — message-first.** The inventory is built PRIMARILY from decodable messages (push,
Message Center, email, SMS) and COMPLEMENTED by in-app / MC CTA signals from `/events`
(`in_app_message`, `in_app_pager`, `ua_mcrap`, `banner - …` customs). CTA-only items carry
just a button label / impression (no full message), so they are tagged `source:"cta_only"`
and their mapping reliability is capped low. `campaign_inventory.build_inventory(...)` unifies
all channels with **no lossy drops** (a min-volume floor is display-only via `bucket_long_tail`);
`split_events(...)` hands the behavioural `location:custom` events to `event_analysis` and the
in-app campaign events here.

**The 6 pillars** (canonical, cross-vertical):
| Pillar | Goal | Typical levers |
|---|---|---|
| Editorial & Content | Maximise content/product discovery | new-content alert, trending, curation, personalised reco, newsletter, live companion |
| Onboarding & Adoption | Activate new users; drive first value | welcome, opt-in/re-opt-in ask, first-action activation, feature education, account creation, cross-device |
| Service & Transactional | Anchor usage with useful/real-time messaging | order/booking status, confirmations, security alerts, reminders, real-time alerts, balance info |
| Lifecycle & Retention | Retain: reactivate, prevent churn, renew | inactive reactivation, win-back, anti-churn, renewal, birthday, abandonment recovery |
| Engagement & Data | Qualify audience via zero/first-party data | NPS/surveys, progressive profiling, gamification, contests, votes, referral |
| Commercial & Monetization | Convert: upsell, cross-sell, promote, subscribe | upsell premium, free trial, promotions, coupons, abandoned-cart offers, loyalty offers |

**Detection — language-aware, high-recall, name-first, content-fallback:**
1. **Detect the label's language** (`detect_lang`, FR/EN heuristic) so tokens are interpreted
   in their own language; aliases stay bilingual.
2. **Name-first, graded, high-recall.** Normalise the `message_name` (accents dropped, alnum
   tokens) and score each catalogue lever by **bilingual EN/FR alias overlap with inflection
   tolerance**: exact token = 1.0, **stem-equal** (light FR/EN stemming, e.g. `decouvrez`~
   `decouvre`, `inscris`~`inscription` family) = 0.85, compound/substring alias ≥5 chars = 0.7,
   **shared 4-char prefix = 0.5** (the broad, recall-first tier). The threshold is deliberately
   low: a partial hit yields a (low-reliability) candidate rather than "no match" — **a broad
   association that may be wrong beats missing a probable one**.
3. **Pillar-priority disambiguation.** When several levers hit, an intent-specific lever
   outranks a generic one via a `priority`/specificity weight (pillar default, overridable per
   lever in `campaign_playbook.json`). E.g. "Je crée ma Carte Club" → `account_creation`
   (onboarding, priority 6), not `loyalty_offer` (commercial); "Je cumule avec la Carte Club"
   stays `loyalty_offer`. Ties then break on vertical relevance. Priority is a tie-break + mild
   score weight, never a hard override (a strong generic match still beats a weak specific one).
4. **Content fallback.** When the name yields no match, pass `bodies={push_uuid: text}` (the
   decoded pushbody **notification text** and/or **Message Center HTML**) — the same scoring
   runs on the body, tagged `basis=content`. Use this for UNICAST/ambiguously-named sends.

**Reliability (numeric, everywhere the mapping is uncertain).** Every mapping exposes
`reliability` ∈ [0,1] = **match quality × basis/source ceiling**: message **name** up to 0.95
(→ High), **body/content** ≤ 0.60 (→ Medium), **`cta_only`** ≤ 0.45 (→ Medium at best). The
High/Medium/Low `confidence` is derived from it (≥0.70 High, ≥0.45 Medium, else Low). Surface
the score with `report_interactive.reliability_pill(score, lang)` so broad matches are shown,
never hidden, but always flagged. **In the report, explain to the reader that this
reliability column/pill is the CONFIDENCE OF THE QUALIFICATION** — i.e. how sure we are the
campaign is correctly mapped to its pillar & lever (High/Medium/Low) — and **not** a
performance metric. `classify_one` also returns `lang`, `basis`, `source` and the
`matched_tokens`.

**The vocabulary is FR/EN only, and the classifier now says so.** On a body written in a
third language the content fallback stops being a fallback and becomes pattern noise: a
German account matched 30 campaigns from content and got 28 of them wrong in one direction,
returning partner coupon pushes as `welcome_onboarding` — which would have shown the client
running the very onboarding programme the review concluded they were missing. So
`covered_by_vocabulary(body_text)` gates the fallback, and a body carrying no French or
English function word comes back `basis="unsupported language"`, `lever=None`. **Treat that
as a signal, not a gap**: if a run returns many of them, the campaign layer has to be read by
someone who speaks the language, and the playbook coverage section must say so rather than
report the classified remainder as if it were the whole book.

**Vertical relevance & "recommended".** Each lever carries a base relevance plus per-vertical
overrides in `campaign_playbook.json`; `relevance(lever, vertical) = verticals.get(vertical,
base)`. A lever is **recommended for the vertical** when relevance ≥ 3. The vertical is
resolved from the brand research (same key family as `benchmarks.json`; `vertical_map`
handles aliases, e.g. `telecom → utility_productivity`).

**Maturity (per pillar) — `pillar_maturity(...)`:**
- **Coverage %** = recommended levers the client already runs (matched at **reliability ≥ 0.45**,
  i.e. ≥ Medium) / recommended levers for the vertical. Tier: ≥70% Mastered, ≥45% In
  consolidation, ≥20% Emerging, else Untapped. Low-reliability (broad `cta_only`) matches stay
  visible in the report but do **not** inflate coverage.
- **Automation share** within the pillar (by campaign count and by sends) and **volume
  share** of total sends.
- **Business stake + key figure** from `campaign_playbook.json` `vertical_stakes[vertical]`
  (falls back to `all_verticals`). Drives the matrix's "Business stake" column and the
  strategic-priority cards. Key figures are contextual → tag `[Brand context]`, confidence
  ≤ Medium.

**Industrialization mix — `automation_mix(...)` (DEPRECATED in the report):** the function
still computes the one-shot vs automated split (by count AND by sends), but the **"today vs
target" viz is no longer shipped** in the standard report — the today-vs-target framing was
dropped for confusing readers. Keep the automated-vs-one-shot read where it is factual: the
**per-channel campaign typology** section, and (optionally) a single account-level
recommendation to rebalance toward automated lifecycle/service.

**Recommended new campaigns — `recommend_campaigns(...)`:** the vertical-recommended levers
NOT run yet, ranked by relevance (× reachable base when provided), each carrying its pillar,
default typology, channels and the business stake it serves. **Treat these as a STARTING POINT
only** — in the report, rewrite each as a concrete proposal **tailored to the brand's business
model & current context** (brand research: recent news, strategy, challenges, competitors) so
the "campaigns to launch" are genuinely relevant to THIS brand, not a generic lever list.
Likewise, the per-pillar **"recommended" use cases in `pillar_coverage`** should be sector/
brand-adapted best-practice ideas (marketer-authored), not raw generic lever labels. Tagged
`[Data+Context]`, confidence ≤ Medium (they rest on detection coverage + vertical guidance +
brand context, not a measured gap in outcome).

**Personalization depth ladder.** Position what the client can already personalise on across
three levels — Level 1 Identity & profile, Level 2 Behaviour & content, Level 3 Context &
prediction — from the data actually present (`/devices` attributes, the event taxonomy from
`event_analysis.py`, custom events). Mark each data point available/not, and note that
deeper targeting typically reduces pressure while lifting performance (state as context).

**Confidence.** The whole layer is contextual and driven by the numeric `reliability`: message
name up to High, content ≤ Medium, `cta_only` ≤ Medium, and the maturity/recommendation/priority
outputs ≤ Medium. Always surface the reliability score + detection basis (name/content/cta_only)
and that stakes/key-figures are external context.
