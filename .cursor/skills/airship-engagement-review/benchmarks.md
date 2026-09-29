# Industry benchmarks (engagement review)

Source: **Airship User Engagement (UA) Benchmarks** · file `Q2_2026_UA_Benchmarks_07.09.2026.xlsx` · published **2026-Q2** · region **global** · imported 2026-07-10.

Machine-readable copy: `benchmarks.json` (scripts read that). Regenerate with
`python scripts/import_benchmarks.py <file.xlsx>` when a new quarter arrives.

## How the skill uses this file
1. Determine the client's **industry** (confirm with the user; default = deduced from
   brand research) and match it to a vertical below via its `aliases`.
2. Show the client KPI next to the vertical **median (p50)** and the **[p10–p90] range**,
   tagged `[Data]`, with the gap (points or ×). Percentiles: Low=10th, Medium=50th, High=90th.
3. **Align definition + device family + denominator**: opt-in↔opt-in, per-platform↔per-platform.
   `sends_per_user_month` is **per MONTH** — multiply a weekly client pressure by ~4.33 to compare.
4. Always cite source + quarter + region. **No region/locale split** (global sample).
5. **Confidence capped at Medium** (external/contextual). No matching vertical / metric →
   state "industry benchmark not available"; **never fabricate**.

> Notes: Percentiles per Airship Overview legend: Low=10th, Medium=50th (median), High=90th. Opt-in/open/sends split by device family (ios/android/web); message_center_read_rate is vertical-only. sends_per_user_month is PER MONTH (multiply a weekly client pressure by ~4.33 to compare). Global sample; no region/locale split.

## Metric keys
| Key | Meaning | Split by |
|---|---|---|
| `optin_rate` | Push opt-in rate | device_family |
| `direct_open_rate` | Direct open rate (directly tapped push / sends) | device_family |
| `influenced_open_rate` | Influenced open rate (app opened <=12h of push / sends) | device_family |
| `sends_per_user_month` | Push sends per user per MONTH | device_family |
| `message_center_read_rate` | Message Center / rich page read rate | vertical_only |

## Verticals & values

### All_verticals  (`all_verticals`)
_aliases: all, overall, cross-industry, baseline, global_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 49.4% [29.5–73.5] | 50.3% [25.3–73.9] | — |
| Direct open rate | 2.5% [0.6–6.8] | 3.1% [0.8–9.8] | 0.4% [0.0–1.3] |
| Influenced open rate | 14.1% [3.3–69.9] | 19.9% [3.8–75.6] | — |
| Sends/user/month | 7.7 [0.7–214.0] | 4.6 [0.5–192.1] | — |
| Msg Center read rate | — | — | 14.8% [0.3–41.3] |

### Business  (`business`)
_aliases: b2b, professional, enterprise, saas_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 56.2% [34.1–79.2] | 54.9% [25.9–79.2] | — |
| Direct open rate | 3.0% [0.4–10.5] | 4.2% [0.8–13.3] | 0.4% [0.0–1.1] |
| Influenced open rate | 20.0% [3.7–136.8] | 29.1% [7.2–165.5] | — |
| Sends/user/month | 7.3 [0.5–100.4] | 4.7 [0.4–51.5] | — |
| Msg Center read rate | — | — | 3.9% [0.5–21.4] |

### Charities, Foundations, and Non-Profit  (`charities_foundations_and_non_profit`)
_aliases: non-profit, nonprofit, charity, foundation, ngo_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 53.7% [31.6–61.0] | 57.1% [44.5–62.9] | — |
| Direct open rate | 8.6% [3.0–17.2] | 11.9% [5.1–14.2] | — |
| Influenced open rate | 26.7% [7.8–41.4] | 26.1% [18.0–42.8] | — |
| Sends/user/month | 1.4 [0.6–4.3] | 1.1 [0.4–2.3] | — |
| Msg Center read rate | — | — | 1.4% [0.7–14.0] |

### Education  (`education`)
_aliases: edtech, school, university, learning, e-learning_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 75.5% [32.1–87.8] | 30.6% [18.2–72.0] | — |
| Direct open rate | 2.4% [0.3–7.9] | 3.2% [0.9–5.9] | 0.0% [0.0–0.0] |
| Influenced open rate | 18.2% [1.0–55.1] | 30.3% [5.3–48.7] | — |
| Sends/user/month | 10.6 [0.9–30.4] | 2.2 [0.7–29.9] | — |
| Msg Center read rate | — | — | 15.5% [5.8–26.6] |

### Entertainment  (`entertainment`)
_aliases: streaming, ott, vod, music, video, movies_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 47.8% [25.2–63.9] | 47.0% [27.7–58.5] | — |
| Direct open rate | 1.3% [0.4–5.6] | 1.7% [0.4–9.2] | 0.3% [0.2–0.8] |
| Influenced open rate | 13.1% [3.3–67.3] | 14.5% [2.5–103.2] | — |
| Sends/user/month | 4.2 [0.2–136.1] | 4.2 [0.5–84.3] | — |
| Msg Center read rate | — | — | 2.3% [0.1–39.0] |

### Finance & Insurance  (`finance_insurance`)
_aliases: bank, banking, insurance, assurance, fintech, finance, banque_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 56.3% [45.1–71.2] | 53.8% [36.1–70.9] | — |
| Direct open rate | 3.7% [2.5–5.7] | 3.4% [2.3–6.5] | 0.8% [0.1–1.8] |
| Influenced open rate | 47.4% [26.3–65.3] | 37.8% [24.6–53.9] | — |
| Sends/user/month | 2.1 [0.6–7.5] | 1.2 [0.5–5.2] | — |
| Msg Center read rate | — | — | 5.2% [0.1–22.9] |

### Food & Drink  (`food_drink`)
_aliases: qsr, restaurant, food, drink, delivery, fast food_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 59.0% [30.4–75.7] | 54.6% [30.8–83.9] | — |
| Direct open rate | 2.2% [0.8–7.3] | 2.5% [0.6–8.5] | 1.5% [1.3–1.8] |
| Influenced open rate | 17.1% [6.9–48.8] | 13.1% [0.5–50.4] | — |
| Sends/user/month | 3.9 [0.8–15.7] | 2.6 [0.3–12.4] | — |
| Msg Center read rate | — | — | 6.7% [2.3–21.3] |

### Gambling, Gaming  (`gambling_gaming`)
_aliases: gaming, games, casino, betting, gambling, igaming_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 41.3% [22.7–63.5] | 55.7% [26.4–72.3] | — |
| Direct open rate | 1.6% [0.2–4.8] | 2.6% [0.9–6.3] | 1.0% [0.3–2.5] |
| Influenced open rate | 49.2% [11.0–171.3] | 55.5% [7.1–204.0] | — |
| Sends/user/month | 2.7 [0.4–33.5] | 1.6 [0.3–29.1] | — |
| Msg Center read rate | — | — | 3.0% [0.4–24.8] |

### Government  (`government`)
_aliases: public sector, gov, administration, civic_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 59.5% [39.1–83.2] | 63.4% [27.6–78.7] | — |
| Direct open rate | 8.5% [0.7–20.4] | 4.2% [0.8–23.6] | — |
| Influenced open rate | 22.0% [3.1–77.6] | 16.2% [3.7–162.8] | — |
| Sends/user/month | 1.8 [0.1–15.8] | 4.8 [0.4–20.7] | — |
| Msg Center read rate | — | — | 2.2% [0.5–3.1] |

### Media  (`media`)
_aliases: news, publishing, broadcaster, press, journalism, tv, magazine_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 39.2% [29.7–60.8] | 38.9% [16.9–57.9] | — |
| Direct open rate | 1.9% [0.8–4.0] | 2.4% [0.5–5.8] | 0.3% [0.0–0.7] |
| Influenced open rate | 6.5% [2.8–14.2] | 8.0% [2.8–19.3] | — |
| Sends/user/month | 130.8 [12.7–407.5] | 157.4 [7.5–415.9] | — |
| Msg Center read rate | — | — | 0.2% [0.1–4.8] |

### Medical, Health & Fitness  (`medical_health_fitness`)
_aliases: health, fitness, medical, wellness, healthcare, pharma_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 51.1% [26.6–70.6] | 55.9% [26.2–75.7] | — |
| Direct open rate | 5.8% [0.9–20.3] | 7.1% [0.4–26.0] | 0.6% [0.6–0.6] |
| Influenced open rate | 23.6% [5.7–108.3] | 29.1% [7.1–132.6] | — |
| Sends/user/month | 1.0 [0.3–8.3] | 1.3 [0.3–9.3] | — |
| Msg Center read rate | — | — | 0.3% [0.1–2.7] |

### Retail  (`retail`)
_aliases: ecommerce, e-commerce, grocery, distribution, fashion, shopping, fmcg, supermarket, commerce, marketplace_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 43.0% [19.2–64.3] | 47.5% [22.0–66.4] | — |
| Direct open rate | 1.7% [0.5–5.6] | 2.6% [1.0–9.9] | 0.4% [0.2–1.0] |
| Influenced open rate | 10.2% [3.6–37.9] | 12.0% [4.4–57.8] | — |
| Sends/user/month | 8.6 [1.1–29.9] | 8.4 [0.8–25.3] | — |
| Msg Center read rate | — | — | 2.1% [0.1–15.3] |

### Social  (`social`)
_aliases: social network, dating, community, messaging_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 39.5% [17.0–75.3] | 54.0% [17.5–60.7] | — |
| Direct open rate | 2.6% [1.4–7.8] | 5.7% [1.1–6.7] | — |
| Influenced open rate | 14.9% [2.1–33.3] | 13.4% [4.2–24.2] | — |
| Sends/user/month | 11.9 [1.4–105.8] | 21.5 [1.8–116.8] | — |
| Msg Center read rate | — | — | — |

### Sports & Recreation  (`sports_recreation`)
_aliases: sports, recreation, outdoor, league_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 49.3% [32.7–65.7] | 54.4% [31.6–66.4] | — |
| Direct open rate | 1.7% [0.5–3.9] | 2.2% [0.7–4.3] | 0.0% [0.0–0.8] |
| Influenced open rate | 6.7% [2.2–23.0] | 8.5% [2.7–27.5] | — |
| Sends/user/month | 14.1 [2.3–209.7] | 15.8 [2.3–212.0] | — |
| Msg Center read rate | — | — | 27.7% [9.0–47.4] |

### Travel & Transportation  (`travel_transportation`)
_aliases: travel, transport, airline, hospitality, mobility, hotel, transportation_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 57.2% [26.4–78.0] | 56.8% [20.2–74.7] | — |
| Direct open rate | 3.2% [0.9–10.8] | 6.0% [2.0–16.7] | 1.1% [0.6–2.0] |
| Influenced open rate | 28.6% [5.9–169.3] | 40.9% [10.9–145.5] | — |
| Sends/user/month | 2.0 [0.1–17.7] | 1.8 [0.1–11.2] | — |
| Msg Center read rate | — | — | 7.3% [0.3–24.3] |

### Utility & Productivity  (`utility_productivity`)
_aliases: utility, productivity, tools, telecom, telco, operator, carrier_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 60.4% [30.5–83.2] | 61.0% [27.3–84.2] | — |
| Direct open rate | 3.6% [0.6–12.2] | 6.2% [0.8–17.1] | 0.2% [0.1–5.3] |
| Influenced open rate | 25.0% [5.0–130.1] | 22.3% [5.1–88.4] | — |
| Sends/user/month | 3.3 [0.3–54.8] | 1.6 [0.1–20.4] | — |
| Msg Center read rate | — | — | 4.8% [0.2–18.4] |

