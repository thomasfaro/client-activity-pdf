# Industry benchmarks (engagement review)

Source: **Airship User Engagement (UA) Benchmarks** · file `Q1_2026_UA_Benchmarks_04.02.2026.xlsx` · published **2026-Q1** · region **global** · imported 2026-06-23.

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
| Opt-in rate | 49.4% [29.6–73.5] | 50.7% [25.6–73.5] | — |
| Direct open rate | 2.6% [0.7–6.7] | 3.2% [0.8–9.8] | 0.4% [0.0–1.3] |
| Influenced open rate | 13.1% [3.5–67.7] | 19.6% [4.0–72.2] | — |
| Sends/user/month | 8.9 [0.7–205.6] | 5.1 [0.5–187.9] | — |
| Msg Center read rate | — | — | 14.5% [0.3–38.9] |

### Business  (`business`)
_aliases: b2b, professional, enterprise, saas_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 55.0% [33.5–79.1] | 54.8% [25.5–80.5] | — |
| Direct open rate | 3.4% [0.6–10.7] | 4.2% [1.0–14.4] | 0.4% [0.0–0.9] |
| Influenced open rate | 18.5% [4.5–115.1] | 28.7% [6.7–133.8] | — |
| Sends/user/month | 6.8 [0.5–108.9] | 5.4 [0.4–40.8] | — |
| Msg Center read rate | — | — | 3.7% [0.6–29.6] |

### Charities, Foundations, and Non-Profit  (`charities_foundations_and_non_profit`)
_aliases: non-profit, nonprofit, charity, foundation, ngo_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 54.0% [34.8–68.7] | 54.5% [46.0–62.9] | — |
| Direct open rate | 11.4% [3.0–19.8] | 4.4% [4.4–4.4] | — |
| Influenced open rate | 21.6% [9.3–33.9] | 17.0% [17.0–17.0] | — |
| Sends/user/month | 3.0 [0.9–5.1] | 2.8 [2.8–2.8] | — |
| Msg Center read rate | — | — | 10.6% [5.4–15.8] |

### Education  (`education`)
_aliases: edtech, school, university, learning, e-learning_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 75.8% [36.0–87.7] | 34.6% [22.2–75.7] | — |
| Direct open rate | 2.4% [0.3–7.8] | 3.6% [0.7–6.4] | 0.0% [0.0–0.0] |
| Influenced open rate | 13.8% [1.0–52.2] | 30.5% [4.4–52.1] | — |
| Sends/user/month | 8.0 [1.4–29.8] | 2.7 [0.8–30.2] | — |
| Msg Center read rate | — | — | 12.7% [4.9–22.2] |

### Entertainment  (`entertainment`)
_aliases: streaming, ott, vod, music, video, movies_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 48.5% [27.5–65.3] | 48.9% [26.4–62.7] | — |
| Direct open rate | 1.3% [0.4–6.1] | 1.5% [0.4–7.5] | 0.4% [0.2–0.9] |
| Influenced open rate | 10.9% [2.8–62.5] | 14.6% [2.1–80.2] | — |
| Sends/user/month | 5.5 [0.4–129.2] | 5.0 [0.4–101.1] | — |
| Msg Center read rate | — | — | 1.8% [0.1–29.0] |

### Finance & Insurance  (`finance_insurance`)
_aliases: bank, banking, insurance, assurance, fintech, finance, banque_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 56.1% [44.8–70.7] | 54.7% [38.3–71.3] | — |
| Direct open rate | 3.8% [2.7–6.1] | 3.6% [2.3–7.0] | 0.4% [0.1–1.3] |
| Influenced open rate | 47.2% [25.7–64.9] | 39.1% [26.4–60.5] | — |
| Sends/user/month | 2.0 [0.7–7.3] | 1.2 [0.5–4.7] | — |
| Msg Center read rate | — | — | 5.5% [0.1–24.5] |

### Food & Drink  (`food_drink`)
_aliases: qsr, restaurant, food, drink, delivery, fast food_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 60.1% [30.4–75.3] | 55.7% [30.2–86.5] | — |
| Direct open rate | 2.3% [1.0–7.1] | 2.8% [0.3–9.6] | 1.7% [1.6–1.9] |
| Influenced open rate | 18.0% [7.4–61.9] | 15.1% [0.8–59.6] | — |
| Sends/user/month | 4.0 [1.0–13.9] | 2.9 [0.5–11.1] | — |
| Msg Center read rate | — | — | 6.4% [2.6–21.8] |

### Gambling, Gaming  (`gambling_gaming`)
_aliases: gaming, games, casino, betting, gambling, igaming_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 41.8% [22.7–62.6] | 56.6% [22.1–69.6] | — |
| Direct open rate | 1.7% [0.2–4.8] | 2.4% [0.8–7.5] | 0.9% [0.3–1.5] |
| Influenced open rate | 52.7% [9.6–236.1] | 45.9% [13.0–197.0] | — |
| Sends/user/month | 2.8 [0.4–34.5] | 1.7 [0.4–33.7] | — |
| Msg Center read rate | — | — | 7.7% [0.3–43.0] |

### Government  (`government`)
_aliases: public sector, gov, administration, civic_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 59.1% [38.9–84.1] | 64.8% [27.5–71.9] | — |
| Direct open rate | 9.7% [0.8–27.1] | 2.6% [0.8–19.3] | — |
| Influenced open rate | 17.4% [4.1–122.6] | 15.5% [4.9–83.1] | — |
| Sends/user/month | 3.8 [0.3–19.9] | 3.2 [0.7–26.8] | — |
| Msg Center read rate | — | — | 2.7% [0.6–5.9] |

### Media  (`media`)
_aliases: news, publishing, broadcaster, press, journalism, tv, magazine_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 39.1% [29.5–60.0] | 39.8% [18.9–57.8] | — |
| Direct open rate | 2.2% [0.8–5.0] | 2.5% [0.6–6.2] | 0.4% [0.0–0.9] |
| Influenced open rate | 6.3% [3.0–13.5] | 8.1% [3.0–19.2] | — |
| Sends/user/month | 134.8 [12.9–393.5] | 161.1 [9.3–414.4] | — |
| Msg Center read rate | — | — | 0.2% [0.1–5.5] |

### Medical, Health & Fitness  (`medical_health_fitness`)
_aliases: health, fitness, medical, wellness, healthcare, pharma_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 51.5% [30.0–71.2] | 57.3% [27.6–76.1] | — |
| Direct open rate | 5.3% [0.9–22.0] | 8.4% [1.8–28.1] | 0.4% [0.4–0.4] |
| Influenced open rate | 26.6% [6.9–136.1] | 33.5% [7.4–148.2] | — |
| Sends/user/month | 1.2 [0.3–10.2] | 1.2 [0.2–13.7] | — |
| Msg Center read rate | — | — | 3.2% [0.8–5.4] |

### Retail  (`retail`)
_aliases: ecommerce, e-commerce, grocery, distribution, fashion, shopping, fmcg, supermarket, commerce, marketplace_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 43.5% [19.9–63.9] | 49.3% [21.6–67.0] | — |
| Direct open rate | 1.8% [0.6–5.1] | 2.9% [0.8–8.7] | 0.6% [0.2–1.4] |
| Influenced open rate | 9.7% [4.2–37.8] | 11.8% [4.0–46.5] | — |
| Sends/user/month | 9.6 [1.1–30.6] | 8.6 [0.4–26.0] | — |
| Msg Center read rate | — | — | 1.6% [0.4–15.9] |

### Social  (`social`)
_aliases: social network, dating, community, messaging_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 42.3% [18.3–70.9] | 53.1% [23.9–61.9] | — |
| Direct open rate | 2.7% [1.1–5.1] | 5.2% [1.2–7.0] | — |
| Influenced open rate | 15.0% [3.3–38.9] | 14.4% [4.6–24.7] | — |
| Sends/user/month | 10.2 [1.2–96.3] | 14.0 [1.4–88.5] | — |
| Msg Center read rate | — | — | — |

### Sports & Recreation  (`sports_recreation`)
_aliases: sports, recreation, outdoor, league_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 49.0% [31.6–64.3] | 54.9% [27.9–64.6] | — |
| Direct open rate | 1.5% [0.7–4.8] | 2.2% [0.5–4.2] | 0.0% [0.0–0.6] |
| Influenced open rate | 6.0% [2.6–22.7] | 8.3% [2.3–28.2] | — |
| Sends/user/month | 24.4 [1.8–191.2] | 24.4 [1.4–258.9] | — |
| Msg Center read rate | — | — | 26.2% [9.9–44.7] |

### Travel & Transportation  (`travel_transportation`)
_aliases: travel, transport, airline, hospitality, mobility, hotel, transportation_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 60.4% [32.1–82.1] | 56.7% [24.5–76.3] | — |
| Direct open rate | 3.2% [1.1–11.8] | 6.1% [2.0–15.9] | 1.2% [0.5–2.2] |
| Influenced open rate | 27.3% [6.4–160.5] | 38.8% [8.9–153.6] | — |
| Sends/user/month | 1.9 [0.2–21.0] | 1.4 [0.1–8.7] | — |
| Msg Center read rate | — | — | 9.3% [0.5–26.5] |

### Utility & Productivity  (`utility_productivity`)
_aliases: utility, productivity, tools, telecom, telco, operator, carrier_

| Metric | iOS | Android | Web/All |
|---|---|---|---|
| Opt-in rate | 59.8% [32.2–82.5] | 60.2% [31.0–84.8] | — |
| Direct open rate | 3.5% [0.5–12.7] | 5.7% [0.7–17.5] | 0.2% [0.1–5.9] |
| Influenced open rate | 27.6% [5.9–116.9] | 23.3% [6.0–110.9] | — |
| Sends/user/month | 5.6 [0.1–49.9] | 2.5 [0.0–25.3] | — |
| Msg Center read rate | — | — | 5.3% [0.2–30.1] |

