# Custom-event catalog by vertical (engagement review)

Source: **Airship — Data Collection by Vertical (best-practice event & attribute catalog)** · file `Data Collection by Vertical.xlsx` · imported 2026-07-29.

Machine-readable copy: `event_catalog.json` (scripts read that). Regenerate with
`python scripts/import_event_catalog.py "Data Collection by Vertical.xlsx"`.

## How the skill uses this file
1. Resolve the client's vertical (from benchmarks industry) to a book vertical via
   `vertical_map` (fallback `all_verticals`).
2. `event_analysis.classify_event()` matches each client custom event to a catalog
   event/category with a confidence level (name tokens + aliases).
3. Conversion KPIs are flagged from the matched category (`is_conversion`, `kpi_kind`).
4. `value_property` / `has_currency_property` tell whether an event *should* carry a
   monetary amount — used to spot 'sent but without conversion value' opportunities.
5. Catalog events the client does NOT send become 'send more to Airship' opportunities.

> Notes: Best-practice custom events & attributes per vertical. 'Category' is the use-case grouping used in the workbook (Purchase, Loyalty, Engagement, In-session Experience, ...), distinct from the canonical 'categories' list. value_property = the event's monetary property (amount/value/price/...) when one exists; has_currency_property flags an explicit 'currency' property. kpi_kind/is_conversion are derived from the category (see import script). This catalog is guidance, not the client's data.

## Vertical mapping (benchmark industry -> book vertical)
| Benchmark vertical | Book vertical |
|---|---|
| `retail` | `retail` |
| `media` | `media` |
| `entertainment` | `media` |
| `finance_insurance` | `fintech` |
| `gambling_gaming` | `casino_gaming` |
| `sports_recreation` | `sport_gaming` |
| `travel_transportation` | `travel` |
| `food_drink` | `recipes_cooking` |
| _(any other)_ | `all_verticals` |

## Canonical event categories

`Account registration`, `Ad display`, `Add to cart`, `Add to wishlist`, `Browse content/product`, `Cancellation`, `Click`, `Confirmation`, `Consume content/product`, `Delivery`, `Expiration`, `Feature usage`, `Location/Geofence`, `Login`, `Logout`, `Loyalty`, `Offer`, `Preorder`, `Purchase`, `Remove from cart`, `Remove from wishlist`, `Reservation`, `Save content/product`, `Share content/product`, `Star content/product`, `Transaction failure`, `Transaction success`, `Update cart`, `Update profile`, `Update wishlist`, `View`

## Recommended events by vertical

### all verticals  (`all_verticals`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `account_created` | Account registration | usage | — | — | — |
| `logged_in` | Login | usage | — | — | — |
| `logged_out` | Logout | usage | — | — | — |
| `preferences_changed` | In-session Experience | usage | — | — | — |
| `added_to_cart` | Add to cart | business | yes | `total_amount` | — |
| `cart_abandoned` | Engagement | usage | — | `total_amount` | — |
| `purchased` | Purchase | business | yes | `total_amount` | — |
| `loyalty_created` | Loyalty | loyalty | yes | — | — |
| `loyalty_tier_upgrade` | Loyalty | loyalty | yes | — | — |
| `points_redeemed` | Loyalty | loyalty | yes | — | — |

### Casino & Gaming  (`casino_gaming`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `stadium_push_triggered` | Location/Geofence | usage | — | — | — |
| `bet_placed` | Purchase | business | yes | `bet_amount` | — |
| `bets_started` | Purchase | business | yes | `bet_amount` | — |
| `winnings_withdrawn` | Transaction success | business | yes | `amount` | — |
| `winnings_reinvested` | Transaction success | business | yes | `amount` | — |
| `review_prompt_sent` | In-session Experience | usage | — | — | — |
| `gaming_session_started` | Feature usage | usage | — | `total_win_loss` | — |
| `gaming_preference_updated` | In-session Experience | usage | — | — | — |
| `vip_host_assigned` | In-session Experience | usage | — | — | — |
| `gaming_session_completed` | Feature usage | usage | — | `final_win_loss_amount` | — |

### EV Charging & Fuel  (`ev_charging_fuel`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `lock_screen_loyalty_prompt` | Location/Geofence | usage | — | — | — |
| `points_balance_updated` | Loyalty | loyalty | yes | `transaction_value` | — |
| `pos_signup_prompt` | Offer | business | yes | — | — |
| `charge_session_started` | Feature usage | usage | — | — | — |
| `fuel_purchase` | Purchase | business | yes | `total_amount` | — |
| `preferred_station_updated` | In-session Experience | usage | — | — | — |
| `vehicle_registered` | Feature usage | usage | — | — | — |
| `charge_preference_updated` | In-session Experience | usage | — | — | — |
| `charge_session_completed` | Feature usage | usage | — | `total_amount` | yes |

### FinTech  (`fintech`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `wallet_pass_downloaded` | Loyalty | loyalty | yes | — | — |
| `check_deposited_via_mobile` | In-session Experience | usage | — | `check_amount` | — |
| `kyc_submitted` | Account registration | usage | — | — | — |
| `kyc_verified` | Account registration | usage | — | — | — |
| `fraud_alert_confirmed` | In-session Experience | usage | — | — | — |
| `unusual_login_attempt` | Location/Geofence | usage | — | — | — |
| `high_risk_transaction` | Transaction success | business | yes | `amount` | — |
| `account_status_changed` | In-session Experience | usage | — | — | — |
| `card_activated` | Feature usage | usage | — | — | — |
| `contact_preference_updated` | In-session Experience | usage | — | — | — |
| `transaction_completed` | Transaction success | business | yes | `amount` | yes |

### Media  (`media`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `subscription_started` | Activation | business | yes | `value` | yes |
| `subscription_renewal` | Activation | business | yes | `value` | — |
| `completed_video_event` | Engagement | usage | — | — | — |
| `read_article_completed` | Engagement | usage | — | — | — |
| `topic_followed` | Engagement | usage | — | — | — |
| `live_story_followed` | Engagement | usage | — | — | — |
| `paid_access_prompt_exposed` | In-session Experience | usage | — | — | — |
| `trial_activated` | Activation | business | yes | — | — |
| `genre_preference_updated` | Update profile | usage | — | — | — |
| `habit_score_calculated` | Engagement | usage | — | — | — |
| `subscription_cancelled` | Activation | business | yes | — | — |
| `subscription_suspended` | Activation | business | yes | — | — |

### Recipes & Cooking  (`recipes_cooking`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `menu_plan_saved` | Save content/product | usage | — | — | — |
| `ingredients_exported_to_list` | Update wishlist | usage | — | — | — |
| `recipe_cooked` | Consume content/product | usage | yes | — | — |
| `grocer_coupon_clipped` | Offer | business | yes | — | — |
| `dietary_preference_updated` | In-session Experience | usage | — | — | — |
| `allergies_updated` | In-session Experience | usage | — | — | — |
| `meal_preference_updated` | In-session Experience | usage | — | — | — |
| `recipe_saved` | Save content/product | usage | — | — | — |
| `recipe_unsaved` | Save content/product | usage | — | — | — |

### Retail  (`retail`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `very_pay_finance_initiated` | Purchase | business | yes | `credit_limit_shown` | — |
| `cross_category_promoted` | In-session Experience | usage | — | — | — |
| `web_to_app_prompt_clicked` | Acquisition | business | yes | — | — |
| `survey_response_captured` | In-session Experience | usage | — | — | — |
| `Low stock in basket` | Engagement | usage | — | — | — |
| `Price drop in basket` | Engagement | usage | — | `original_price` | — |
| `add_to_wishlist` | Add to wishlist | usage | — | — | — |
| `favorite_store_updated` | In-session Experience | usage | — | — | — |
| `payment_method_updated` | Update profile | usage | — | — | — |
| `points_earned` | Loyalty | loyalty | yes | — | — |
| `points_spent` | Loyalty | loyalty | yes | — | — |

### Sport & Gaming  (`sport_gaming`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `bet_placed` | Purchase | business | yes | `bet_amount` | — |
| `bets_started` | Purchase | business | yes | `bet_amount` | — |
| `stadium_push_triggered` | Location/Geofence | usage | — | — | — |
| `score_update_received` | Engagement | usage | — | — | — |
| `survey_response_captured` | In-session Experience | usage | — | — | — |
| `media_interaction` | Engagement | usage | — | — | — |
| `rewards_redeemed` | Feature usage | usage | — | — | — |
| `game_watched` | Engagement | usage | — | — | — |
| `favorite_team_updated` | In-session Experience | usage | — | — | — |
| `favorite_league_updated` | In-session Experience | usage | — | — | — |
| `betting_limit_updated` | Update profile | usage | — | — | — |
| `rewards_tier_changed` | Loyalty | loyalty | yes | — | — |
| `ux_preference_updated` | In-session Experience | usage | — | — | — |

### Travel  (`travel`)

| Event | Category | KPI kind | Conversion | Value prop | Currency |
|---|---|---|---|---|---|
| `booking` | Purchase | business | yes | — | yes |
| `seat_upgrade_purchase` | Purchase | business | yes | — | yes |
| `priority_upgrade_purchase` | Purchase | business | yes | — | yes |
| `bag_check_purchase` | Purchase | business | yes | — | yes |
| `food_purchase` | Purchase | business | yes | — | yes |
| `loyalty_upgrade` | Loyalty | loyalty | yes | — | — |
| `loyalty_enrollment` | Loyalty | loyalty | yes | — | — |
| `loyalty_sign_in` | Loyalty | loyalty | yes | — | — |
| `loyalty_redemption` | Loyalty | loyalty | yes | — | — |
| `check_in_completed` | Transaction success | business | yes | — | — |
| `credits_added` | Loyalty | loyalty | yes | — | — |
| `home_airport_changed` | Update profile | usage | — | — | — |
| `subscription_preferences_added` | Update profile | usage | — | — | — |
| `subscription_preferences_changed` | Update profile | usage | — | — | — |
| `self_service_check_in` | Transaction success | business | yes | — | — |
| `self_service_print_bag_tag` | Transaction success | business | yes | — | — |
| `self_service_rebook` | Transaction success | business | yes | — | — |
| `self_service_seat_change` | Transaction success | business | yes | — | — |
| `self_service_special_meal_selected` | Transaction success | business | yes | — | — |
| `self_service_infant_in_arms_selected` | Transaction success | business | yes | — | — |
| `self_service_airport_services_selected` | Transaction success | business | yes | — | — |
| `travel_documents_complete` | Transaction success | business | yes | — | — |
| `passport_scanned` | Transaction success | business | yes | — | — |
| `touchless_registered` | Transaction success | business | yes | — | — |
| `tsa_precheck_added` | Transaction success | business | yes | — | — |
| `download_mobile_boarding_pass` | Transaction success | business | yes | — | — |
| `flight_delayed` | Transaction failure | usage | — | — | — |
| `flight_cancelled` | Transaction failure | usage | — | `travel_credits_value` | — |
| `gate_changed` | Location/Geofence | usage | — | — | — |
| `baggage_carousel_assigned` | Feature usage | usage | — | — | — |
| `inflight_wifi_purchased` | Purchase | business | yes | `price_usd` | — |
| `cobrand_cc_offer_exposed` | Offer | business | yes | — | — |
| `set_home_airport` | Update profile | usage | — | — | — |
| `city_visited` | Update profile | usage | — | — | — |
| `cart_recovery_purchase` | Purchase | business | yes | — | — |
| `cart_recovery_app` | Purchase | business | yes | — | yes |

