# Campaign playbook - pillars, standard levers & vertical stakes

Human-readable companion to campaign_playbook.json. Used by scripts/campaign_purpose.py to
map a client campaign to a strategic **pillar** + standard **lever** (name-first, bilingual
EN/FR alias overlap, content fallback), compute per-pillar **maturity** (coverage of the
levers recommended for the vertical + automation share) and **recommend** the missing levers.

Detection: relevance(lever, vertical) = lever.verticals.get(vertical, lever.base); a lever is
*recommended for the vertical* when relevance >= 3. Reports API only - content used for
detection comes from decoded perpush/pushbody, never the Content API.

**French text lives in the JSON, not here.** Every pillar carries `label_fr` + `goal_fr`,
every lever a `label_fr`, and vertical stakes a `stake_fr` + `key_figure_fr`; a French report
reads those fields directly. This companion prints the FR *labels* (below) but keeps stakes
and goals in English only, so it stays readable — read the JSON when you need the exact
French wording. Stake translations are **partial by design**: `all_verticals` and `retail`
carry them today, and any vertical without them falls back to the English text. When you edit
the JSON, mirror the label change here; nothing generates this file.

## Pillars

| # | Key | Pillar (EN / FR) | Goal |
|---|-----|------------------|------|
| 1 | `editorial` | Editorial & Content / Éditoriale | Maximise content volume & discovery |
| 2 | `onboarding_adoption` | Onboarding & Adoption / Adoption & Onboarding | Activate new users; drive first value & feature adoption |
| 3 | `service` | Service & Transactional / Servicielle | Anchor usage with useful, real-time & transactional messaging |
| 4 | `lifecycle` | Lifecycle & Retention / Cycle de vie | Retain: reactivate, prevent churn, renew |
| 5 | `engagement_data` | Engagement & Data / Engagement | Grow value: collect zero/first-party data, gamify, qualify audience |
| 6 | `commercial` | Commercial & Monetization / Commerciale | Convert: upsell, cross-sell, promote, subscribe |

## Standard levers by pillar

### Editorial & Content (`editorial`)

| Lever | FR | Default typology | Channels | Description |
|-------|----|------------------|----------|-------------|
| `new_content_alert` - New content / release alert | Alerte nouveau contenu / sortie | automated | push, in_app, email | Notify when a new episode, article, product, collection or program drops. |
| `trending_now` - Trending / most-popular now | Tendances du moment | automated | push, in_app | Push the currently trending, most-watched or best-selling items. |
| `editorial_selection` - Thematic selection / curation | Sélection thématique / curation | one_shot | push, email, in_app | Editorialised thematic bundles that reduce choice overload. |
| `personalized_reco` - Personalised recommendations | Recommandations personnalisées | automated | push, email, in_app | 1:1 content/product recommendations from behaviour and affinity. |
| `newsletter_digest` - Newsletter / recurring digest | Newsletter / digest récurrent | automated | email, push | Scheduled digest (daily/weekly) of the best content or offers. |
| `last_chance_content` - Leaving soon / last chance | Dernière chance / bientôt indisponible | automated | push, email | Content leaving the catalogue soon; drives urgency to consume. |
| `coming_soon_teaser` - Coming soon / teaser | Prochainement / teasing | one_shot | push, email, in_app | Teasing upcoming releases, previews or pre-orders. |
| `live_companion` - Live companion / real-time tracking | Compagnon de direct / live | automated | push, in_app | Second-screen alerts around a live event (kick-off, goals, results). |

### Onboarding & Adoption (`onboarding_adoption`)

| Lever | FR | Default typology | Channels | Description |
|-------|----|------------------|----------|-------------|
| `welcome_onboarding` - Welcome pack / onboarding | Welcome pack / onboarding | automated | push, email, in_app | Welcome series introducing the app to new registrants. |
| `optin_request` - Push / email opt-in request | Demande d'opt-in (push & email) | automated | in_app, push, email | Prime and request notification/email permission (pre-permission + system). |
| `reoptin_permission` - Re-opt-in / permission win-back | Demande de ré-opt-in | automated | in_app, email | Recover users who declined or disabled notifications/email. |
| `first_action_activation` - Activation — first key action | Activation (1re action clé) | automated | push, email, in_app | Nudge the first video/purchase/booking/deposit that defines activation. |
| `feature_education` - Feature discovery / tutorial | Présentation fonctionnalités / tuto | one_shot | in_app, push, email | Educate on new or under-used features (how-to, guided tour). |
| `account_creation` - Account creation nudge | Incitation à la création de compte | automated | in_app, push, email | Convert anonymous/guest users into registered accounts. |
| `cross_device_adoption` - Cross-device adoption (TV / web-to-app) | Adoption multi-écran (TV / web-to-app) | one_shot | push, email, in_app | Drive users to the environment with the best experience & retention. |
| `app_update_prompt` - App update prompt | Incitation à la mise à jour | automated | push, in_app | Encourage updating to the latest app version. |

### Service & Transactional (`service`)

| Lever | FR | Default typology | Channels | Description |
|-------|----|------------------|----------|-------------|
| `order_status` - Order / booking status & delivery | Statut commande / livraison | automated | push, email, sms | Real-time order, delivery, pickup (drive/click & collect) status. |
| `transactional_confirm` - Confirmation / receipt | Confirmation / reçu | automated | email, push, sms | Confirm a transaction, booking, reservation or subscription. |
| `account_security` - Account & security alerts | Alertes compte & sécurité | automated | push, email, sms | Security, login, password, OTP, fraud and email-validation alerts. |
| `reminder_service` - Reminders (appointment / expiry) | Rappels (rendez-vous / échéance) | automated | push, email, sms | Useful reminders: appointments, expirations, things to finish. |
| `realtime_service_alert` - Real-time service alert | Alerte service temps réel | automated | push, sms | Disruption, delay, incident or status alerts on a service. |
| `balance_usage_info` - Balance / consumption info | Info conso / solde | automated | push, email | Data/forfait usage, points balance, invoice or statement availability. |
| `help_support` - Help / how-to support | Aide / prise en main | one_shot | in_app, email, push | Contextual help, FAQ and support to remove friction. |

### Lifecycle & Retention (`lifecycle`)

| Lever | FR | Default typology | Channels | Description |
|-------|----|------------------|----------|-------------|
| `inactive_reactivation` - Inactive reactivation | Relance inactif | automated | push, email | Bring dormant users back before they lapse. |
| `winback` - Win-back lapsed / churned | Win-back / reconquête | automated | email, push | Reconquer users who churned or unsubscribed, often with an incentive. |
| `anti_churn` - Anti-churn / at-risk | Anti-churn / à risque | automated | email, push, in_app | Proactively retain at-risk or cancelling subscribers. |
| `renewal` - Subscription / policy renewal | Renouvellement | automated | email, push, sms | Drive on-time renewal of a subscription, policy or membership. |
| `birthday_anniversary` - Birthday / account anniversary | Anniversaire (client / compte) | automated | email, push | Celebrate a birthday or account anniversary, often with a gift. |
| `abandonment_recovery` - Abandonment recovery (cart / viewing) | Relance abandon (panier / visionnage) | automated | email, push, in_app | Recover an abandoned cart, booking or unfinished viewing/reading. |
| `milestone_retrospective` - Milestone / retrospective | Étape clé / rétrospective | one_shot | email, push, in_app | Yearly wrap-up, usage milestone or personalised retrospective. |

### Engagement & Data (`engagement_data`)

| Lever | FR | Default typology | Channels | Description |
|-------|----|------------------|----------|-------------|
| `survey_nps` - Satisfaction / NPS survey | Enquête satisfaction / NPS | automated | in_app, email, push | Measure satisfaction and collect qualitative feedback. |
| `progressive_profiling` - Progressive profiling / interests | Progressive profiling / intérêts | automated | in_app, email, push | Enrich the profile with declared interests and preferences over time. |
| `gamification` - Games / quiz / gamification | Jeux / quiz / gamification | one_shot | in_app, push, email | Interactive games, quizzes and challenges that drive engagement + data. |
| `contest_sweepstake` - Contest / prize draw | Concours / tirage au sort | one_shot | push, email, in_app | Sweepstakes and contests to boost participation and lead capture. |
| `interactive_vote` - Interactive vote / poll / prediction | Vote / sondage / pronostic | one_shot | in_app, push | Live votes, polls and predictions tied to content or events. |
| `referral_engagement` - Refer a friend / share | Parrainage / partage | automated | push, email, in_app | Encourage sharing and friend referrals to grow the base virally. |

### Commercial & Monetization (`commercial`)

| Lever | FR | Default typology | Channels | Description |
|-------|----|------------------|----------|-------------|
| `upsell_premium` - Upsell to premium / ad-free | Upsell premium / sans pub | automated | push, email, in_app | Upgrade to a premium, ad-free or higher tier. |
| `free_trial` - Free trial offer | Offre d'essai gratuit | one_shot | push, email, in_app | Offer a free trial to convert to a paid subscription. |
| `promotion_offer` - Promotion / flash sale | Promotion / vente flash | one_shot | push, email, in_app | Time-boxed promotions, discounts and flash sales. |
| `cross_sell_product` - Cross-sell / complementary | Cross-sell / produits complémentaires | automated | email, push, in_app | Recommend complementary products or services after a purchase. |
| `abandoned_cart_commercial` - Abandoned cart with incentive | Panier abandonné avec incitation | automated | email, push | Recover a checkout abandonment with a targeted incentive. |
| `seasonal_campaign` - Seasonal / event campaign | Campagne saisonnière / temps fort | one_shot | push, email, in_app | Seasonal peaks: sales, holidays, back-to-school, big events. |
| `coupon_couponing` - Coupon / voucher | Coupon / bon de réduction | automated | push, email, in_app | Personalised coupons, cashback and vouchers. |
| `loyalty_offer` - Loyalty-tier / reward offer | Offre fidélité / récompense | automated | push, email, in_app | Reward loyal members: tiers, exclusive perks and status offers. |

## Vertical business stakes (per pillar)

Powers the strategic-priorities cards and the maturity matrix `Enjeu Business` column.
A vertical missing a pillar falls back to `all_verticals`.

### all_verticals

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Maximise reach & discovery of what you offer | Relevant, editorialised discovery lifts engagement vs a raw catalogue |
| Onboarding & Adoption | Activate new users to first value | Users who complete onboarding retain markedly better |
| Service & Transactional | Anchor daily usage with useful messaging | Transactional/service messages earn the highest open & trust |
| Lifecycle & Retention | Retain the base you already acquired | Acquiring a user costs 5-25x more than retaining one |
| Engagement & Data | Qualify the audience with first-party data | Targeted campaigns can drive ~2.5x clicks and ~6x conversions vs generic |
| Commercial & Monetization | Convert engagement into revenue | Personalised offers outperform mass promotions on ROI |

### media

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Maximise content volume & discovery | ~60% of users feel choice-overload without strong editorialisation |
| Onboarding & Adoption | Activate to first view & drive account creation | Logged-in, activated users are far more retainable & monetisable |
| Service & Transactional | Anchor usage across screens (Mobile + TV) | +30% LTV on users active on 2 screens (Mobile + TV) |
| Lifecycle & Retention | Retain viewers & subscribers | Acquiring a viewer costs 5-25x more than retaining one |
| Engagement & Data | Grow logged, segmentable audience value | Segmented (logged-in) ad inventory sells 2-3x higher CPM |
| Commercial & Monetization | Convert free to premium/ad-free | Subscription is a niche - only ~38% of users reject ads |

### entertainment

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Maximise catalogue discovery & tune-in | Personalised discovery drives session starts vs raw browse |
| Onboarding & Adoption | Activate to first stream fast | First-week viewing strongly predicts subscription survival |
| Service & Transactional | Anchor viewing across devices | Cross-device viewers churn less than single-device |
| Lifecycle & Retention | Retain subscribers & recover lapsed | Voluntary churn is the top threat to SVOD LTV |
| Engagement & Data | Enrich taste profiles for better reco | Richer interest data lifts recommendation CTR |
| Commercial & Monetization | Convert trials & upsell tiers | Trial-to-paid conversion is the core SVOD growth lever |

### retail

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Drive product & catalogue discovery | Personalised product discovery lifts basket size |
| Onboarding & Adoption | Activate to first purchase & loyalty sign-up | First purchase and loyalty enrolment define activation |
| Service & Transactional | Anchor with order, drive & loyalty service | Order/pickup status messages earn the highest engagement |
| Lifecycle & Retention | Retain shoppers & recover carts | Acquiring a shopper costs 5-25x more than retaining one |
| Engagement & Data | Grow loyalty & first-party data | Loyalty members shop more often and share more data |
| Commercial & Monetization | Convert with personalised offers | Targeted coupons beat mass promotions on margin |

### finance_insurance

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Educate on products & guidance | Financial education content builds trust and cross-sell |
| Onboarding & Adoption | Activate first key action (fund / enrol) | Early activation predicts long-term account value |
| Service & Transactional | Anchor with secure, useful alerts | Security & balance alerts are the most-valued messages |
| Lifecycle & Retention | Retain policyholders & renew on time | On-time renewal is the core retention lever |
| Engagement & Data | Qualify needs & risk profile | Better profiling enables relevant cross-sell |
| Commercial & Monetization | Convert cross-sell & upsell | Existing customers convert cross-sell far above cold prospects |

### food_drink

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Drive menu & new-item discovery | New-item and reco pushes drive incremental visits |
| Onboarding & Adoption | Activate to first order & app payment | App-order activation raises visit frequency |
| Service & Transactional | Anchor with order & pickup status | Order-ready alerts drive satisfaction and repeat |
| Lifecycle & Retention | Retain & lift visit frequency | Frequency is the main lever of QSR value |
| Engagement & Data | Grow loyalty & gamified engagement | Gamified loyalty lifts app open frequency |
| Commercial & Monetization | Convert with offers & coupons | Personalised offers drive incremental visits |

### travel_transportation

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Inspire destinations & offers | Inspirational content seeds future bookings |
| Onboarding & Adoption | Activate to first booking | Early booking activation predicts repeat travel |
| Service & Transactional | Anchor with real-time trip service | Trip status & disruption alerts are the most-valued messages |
| Lifecycle & Retention | Retain travellers & recover carts | Booking abandonment recovery is a major revenue lever |
| Engagement & Data | Qualify travel intent & preferences | Intent data enables relevant, timely offers |
| Commercial & Monetization | Convert with timely, targeted offers | Ancillary & timely offers lift booking value |

### sports_recreation

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Maximise live & match discovery | Live alerts drive the most session starts |
| Onboarding & Adoption | Activate to follow teams & first content | Following teams/competitions drives retention |
| Service & Transactional | Anchor with real-time match service | Live score & kick-off alerts are the core utility |
| Lifecycle & Retention | Retain fans across seasons | Off-season re-engagement protects the base |
| Engagement & Data | Grow fan data via votes & predictions | Predictions & votes generate rich first-party data |
| Commercial & Monetization | Convert to premium & betting/commerce | Engaged fans convert best to premium & partners |

### gambling_gaming

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Surface events, odds & new games | Timely event/odds alerts drive session starts |
| Onboarding & Adoption | Activate to first deposit/bet | First deposit is the defining activation event |
| Service & Transactional | Anchor with account & responsible-play service | Security & balance alerts build trust and compliance |
| Lifecycle & Retention | Retain & recover at-risk players | Reactivation and anti-churn protect player value |
| Engagement & Data | Grow engagement via gamification | Gamified mechanics lift frequency and data capture |
| Commercial & Monetization | Convert with targeted bonuses | Personalised bonuses outperform blanket promos |

### utility_productivity

| Pillar | Business stake | Key figure |
|--------|----------------|------------|
| Editorial & Content | Educate on features & value | Feature education lifts adoption of paid capabilities |
| Onboarding & Adoption | Activate to the core habit | Reaching the aha-moment early predicts retention |
| Service & Transactional | Anchor with real-time usage & alerts | Usage/consumption & incident alerts are core utility |
| Lifecycle & Retention | Retain and renew | Habitual usage and renewal drive lifetime value |
| Engagement & Data | Qualify needs & preferences | Preference data enables relevant nudges |
| Commercial & Monetization | Convert to paid tiers | Feature-gated upsell converts engaged users |
