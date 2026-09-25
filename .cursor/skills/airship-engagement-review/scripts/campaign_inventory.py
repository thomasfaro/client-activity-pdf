#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical, multi-channel campaign inventory for the engagement review (no network).

One source of truth for "what campaigns did the client run", built MESSAGE-FIRST:

  PRIMARY   push / Message Center / email / SMS  -> real, decodable messages
            (from the merged push inventory: activity log + responses/list, and
             email/SMS per-message rows). Bodies are decoded from perpush/pushbody
             upstream; here we only consume the shaped rows.
  COMPLEMENT in-app  -> the `/events` feed only exposes CTA names for in-app
            (`in_app_message` / `in_app_pager`) and Message Center engagement
            (`ua_mcrap`), plus in-app `banner - ...` impressions under
            `location:custom`. These carry NO full message, so they are added as a
            LOW-RELIABILITY, `source:"cta_only"` complement — never dropped, but the
            downstream mapping caps their reliability.

Design rules (see plan "Message-first campaign analysis"):
  - NO lossy hard drops. A minimum-volume floor is DISPLAY-only (long tail bucketed
    as "autres / other"), never an exclusion from classification.
  - Behavioural custom events (`location:custom`, excluding `banner - ...`) are NOT
    campaigns; `split_events()` hands them back for `event_analysis` instead.

The canonical campaign shape (compatible with classify_campaigns / campaign_purpose):
    {key, label, channel, source, type, total_sends, push_uuids, label_lang}
  channel in {push, mc, email, sms, in_app}; source in {message, cta_only}.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# in-app "banner - ..." custom events are campaign impressions, not behaviour.
_BANNER_PREFIX = "banner - "

# Markers that a CTA-only in-app campaign is part of an AUTOMATED/recurring program
# (drip day offsets, weekly rendez-vous, onboarding/lifecycle triggers). Everything else
# stays "ambiguous" — with a CTA name alone we cannot assert a true one-shot.
_AUTOMATION_MARKERS = re.compile(
    r"(j\+\d+|rdv du jeudi|rendez-vous|onboarding|welcome|bienvenue|relance|reminder|"
    r"lifecycle|recurring|hebdo|weekly|quotidien|daily|abandon|nurtur|drip)", re.I)


def _infer_type(label: str, loc: str) -> str:
    return "automated_recurring" if _AUTOMATION_MARKERS.search(label or "") else "ambiguous"

# ---- light language hint (kept local so this module has no deps) -------------
_FR_MARKERS = {
    "je", "tu", "vous", "votre", "vos", "mon", "ma", "mes", "le", "la", "les", "des",
    "une", "un", "du", "au", "aux", "pour", "avec", "sur", "chez", "tente", "tentez",
    "cree", "creer", "creez", "inscris", "inscrire", "inscrivez", "rejoins", "rejoignez",
    "decouvre", "decouvrez", "profite", "profitez", "participe", "participez", "vais",
    "veux", "bon", "bons", "offert", "offerte", "cadeau", "jeudi", "rdv", "carte", "club",
    "fidelite", "cagnotte", "bienvenue", "essentiels", "courses", "livraison",
}
_ACCENTS = set("àâäéèêëîïôöùûüç")


def detect_lang(text: Any) -> str:
    """Very light FR/EN detector for a label/identifier ('fr' or 'en')."""
    s = str(text or "").lower()
    if any(ch in _ACCENTS for ch in s):
        return "fr"
    toks = set(re.split(r"[^a-z0-9]+", s))
    return "fr" if (toks & _FR_MARKERS) else "en"


# ---- helpers ----------------------------------------------------------------
def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _clean_banner(name: str) -> str:
    """`banner - promo ciblée - coupons - j+10` -> `promo ciblée - coupons` (family)."""
    b = name[len(_BANNER_PREFIX):]
    b = re.sub(r"\s*-\s*j\+\d+.*$", "", b, flags=re.I)          # drop " - j+7 - ..."
    b = re.sub(r"\s*-\s*(lancement|ba|hm|sm)\b.*$", "", b, flags=re.I)
    return b.strip() or name


def _looks_like_uuid(s: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{6,}(-[0-9a-f]+)*", s.strip().lower()))


# ---- events split (behavioural vs in-app campaigns) -------------------------
def split_events(events: Sequence[dict]) -> Tuple[List[dict], List[dict]]:
    """Partition the raw /events feed.

    Returns (behavioural_custom, inapp_campaign_events):
      - behavioural_custom: `location:custom` events EXCEPT `banner - ...` — feed these
        to `event_analysis.analyze(...)` for the conversion/taxonomy sections.
      - inapp_campaign_events: everything usable as a (complementary) in-app/MC campaign
        signal — `in_app_message`, `in_app_pager`, `ua_mcrap`, and `banner - ...` customs.
    """
    behavioural, inapp = [], []
    for e in events or []:
        loc = (e.get("location") or "").lower()
        name = (e.get("name") or "")
        if loc == "custom" and not name.lower().startswith(_BANNER_PREFIX):
            behavioural.append(e)
        else:
            inapp.append(e)
    return behavioural, inapp


# ---- complementary in-app / MC campaigns (CTA-only) -------------------------
def extract_inapp_campaigns(events: Sequence[dict]) -> List[dict]:
    """Aggregate the CTA-only in-app / MC signal into canonical campaigns.

    Never drops rows on volume; UUID-only / empty titles are skipped as pure noise
    (they carry no interpretable label). Everything else is kept as `source:cta_only`.
    """
    agg: Dict[str, dict] = {}
    for e in events or []:
        loc = (e.get("location") or "").lower()
        raw = (e.get("name") or "").strip()
        cnt = _int(e.get("count"))
        if not raw:
            continue
        low = raw.lower()
        label = channel = None
        if loc == "custom" and low.startswith(_BANNER_PREFIX):
            label, channel = f"In-app banner — {_clean_banner(raw)}", "in_app"
        elif loc == "in_app_message" and low.startswith("button-click-"):
            cta = raw[len("button-click-"):].strip()
            label, channel = f"In-app CTA — {cta}", "in_app"
        elif loc == "in_app_pager":
            cta = re.sub(r"^button-tap-(deep_link|dismiss|next|prev)?-*", "", raw, flags=re.I).strip()
            cta = cta or raw
            label, channel = f"In-app story/pager — {cta}", "in_app"
        elif loc == "ua_mcrap" and low.startswith("button_click:"):
            title = raw[len("button_click:"):].strip()
            if not title or _looks_like_uuid(title):
                continue
            label, channel = f"Message Center — {title}", "mc"
        else:
            continue
        ctype = _infer_type(raw, loc)          # from the RAW name (keeps j+/onboarding markers)
        gkey = f"{channel}\u0001{label.lower()}"
        row = agg.get(gkey)
        if row:
            row["total_sends"] += cnt
            if ctype == "automated_recurring":
                row["type"] = "automated_recurring"
        else:
            agg[gkey] = {"label": label, "channel": channel,
                         "total_sends": cnt, "type": ctype}

    out = []
    for i, row in enumerate(sorted(agg.values(), key=lambda r: -r["total_sends"]), start=1):
        out.append({
            "key": f"cta{i}",
            "label": row["label"],
            "channel": row["channel"],
            "source": "cta_only",
            "type": row["type"],
            "total_sends": row["total_sends"],
            "push_uuids": [],
            "label_lang": detect_lang(row["label"]),
        })
    return out


def _norm_message_campaign(c: dict, default_channel: str) -> dict:
    """Coerce a message-based campaign (push/mc/email/sms) into the canonical shape."""
    label = c.get("label") or c.get("name") or c.get("message_name") or c.get("key") or ""
    return {
        "key": c.get("key") or (c.get("push_uuids") or [None])[0] or label,
        "label": label,
        "channel": (c.get("channel") or default_channel or "push").lower(),
        "source": "message",
        "type": c.get("type") or "ambiguous",
        "total_sends": _int(c.get("total_sends") or c.get("sends")),
        "push_uuids": c.get("push_uuids") or ([c["push_uuid"]] if c.get("push_uuid") else []),
        "label_lang": detect_lang(label),
    }


# ---- builder ----------------------------------------------------------------
def build_inventory(push_campaigns: Optional[Sequence[dict]] = None,
                    email_sms_campaigns: Optional[Sequence[dict]] = None,
                    events: Optional[Sequence[dict]] = None,
                    include_inapp: bool = True) -> dict:
    """Assemble the canonical, multi-channel campaign inventory.

    push_campaigns: message-based push/MC campaigns (e.g. from
        `classify_campaigns.classify(merge_push_inventories()[...])["campaigns"]`);
        each may carry `channel` ("push"/"mc") — defaults to "push".
    email_sms_campaigns: message-based email/SMS campaigns/rows (carry `channel`).
    events: raw /events list; the complementary in-app/MC (CTA-only) signal is
        extracted from it when `include_inapp` is True.
    """
    campaigns: List[dict] = []
    for c in (push_campaigns or []):
        campaigns.append(_norm_message_campaign(c, c.get("channel") or "push"))
    for c in (email_sms_campaigns or []):
        campaigns.append(_norm_message_campaign(c, c.get("channel") or "email"))
    if include_inapp and events:
        campaigns.extend(extract_inapp_campaigns(events))

    campaigns.sort(key=lambda c: c["total_sends"], reverse=True)

    by_channel: Dict[str, dict] = {}
    by_source = {"message": 0, "cta_only": 0}
    for c in campaigns:
        b = by_channel.setdefault(c["channel"], {"campaigns": 0, "sends": 0})
        b["campaigns"] += 1
        b["sends"] += c["total_sends"]
        by_source[c["source"]] = by_source.get(c["source"], 0) + 1

    return {
        "campaigns": campaigns,
        "stats": {
            "total": len(campaigns),
            "by_channel": by_channel,
            "by_source": by_source,
            "message_based": by_source.get("message", 0),
            "cta_only": by_source.get("cta_only", 0),
        },
    }


def bucket_long_tail(campaigns: Sequence[dict], min_sends: int) -> dict:
    """DISPLAY-only: split into shown campaigns vs a bucketed long tail.

    Never used to exclude from classification — only to keep report tables readable.
    """
    shown = [c for c in campaigns if _int(c.get("total_sends")) >= min_sends]
    tail = [c for c in campaigns if _int(c.get("total_sends")) < min_sends]
    return {
        "shown": shown,
        "tail_count": len(tail),
        "tail_sends": sum(_int(c.get("total_sends")) for c in tail),
        "min_sends": min_sends,
    }


# ---- Scene instrumentation grade -------------------------------------------
# Airship's own in-app events tell you a Scene was shown and how it ended. They do not tell
# you what happened inside it: which screen a user abandoned on, whether they completed the
# flow, what they chose. That gap is invisible unless someone looks for it, because the
# dismissal count looks like data — an account can read "69% dismissed" and never notice it
# has no idea what the other 31% did.
#
# Three things are separately observable, and each answers a different question:
#
#   outcomes_named    Do the buttons carry meaningful identifiers? `button-tap-push_opt_in`
#                     says what the user chose; `button-tap-dismiss_button` says only that
#                     they left. Named buttons make the Scene's RESULT readable.
#   screen_transitions  `swipe-0-1` is screen 0 to screen 1 — Airship's pager events do
#                     expose movement between screens, which is more than most accounts
#                     realise they already have.
#   custom_events     Does the app fire its OWN events on the flow? This is the only one
#                     that supports a step-level funnel, because only the app knows what
#                     "completed" means.
#
# Graded rather than described, so the same account reads the same way next quarter.

# Identifiers Airship generates on its own. A Scene whose interactions are all in this set
# is a Scene nobody instrumented.
_GENERIC_CTA = re.compile(
    r"^(user-dismissed|message-click|message-display|button-tap-dismiss_button|"
    r"button-tap-(dismiss|next|prev|previous|skip|close)$|swipe[-\d]*$|"
    r"button-tap-(dismiss|next|prev|previous|skip|close)--)", re.I)
_SWIPE_STEP = re.compile(r"^swipe--?\d+--?-?\d+$", re.I)
# Conservative on purpose: `onboarding_finished` may well be a Scene completion, or an app
# onboarding that has nothing to do with one. Claiming Scene instrumentation off a guess
# would hand the account a grade it has not earned, so only explicit naming counts.
_SCENE_CUSTOM = re.compile(r"(scene|in_?app|pager|story)", re.I)
_INAPP_LOCS = ("in_app_message", "in_app_pager")


def scene_instrumentation(events: Sequence[dict]) -> dict:
    """Grade how much of what happens inside a Scene is measurable. No network.

    Returns `{"volume": 0}` when the account shows no in-app messages at all — §8b then
    stays a legitimate N/A. Any in-app volume at all and the section is required, because
    an account running Scenes blind is exactly the case worth reporting.
    """
    vol = named = generic = swipes = 0
    customs: List[str] = []
    for e in events or []:
        loc = (e.get("location") or "").lower()
        name = (e.get("name") or "").strip()
        cnt = _int(e.get("count"))
        if loc in _INAPP_LOCS:
            vol += cnt
            if _SWIPE_STEP.match(name):
                swipes += cnt
            elif not name.lower().startswith("button-"):
                pass          # `user-dismissed`, `message-click`: not a button press
            elif _GENERIC_CTA.match(name):
                generic += cnt
            else:
                named += cnt
        elif loc == "custom" and _SCENE_CUSTOM.search(name):
            customs.append(name)
    if not vol:
        return {"volume": 0, "grade": None, "dimensions": {}, "missing": []}

    # Share of BUTTON PRESSES that told us which button, not share of all interactions.
    # In-app is dismissal-dominated by nature — roughly 70% on a healthy account — so
    # measuring against total interactions would fail every client for a reason that has
    # nothing to do with how they configured their Scenes.
    # The second condition guards the degenerate case: three named taps against 100k
    # displays satisfies the ratio and still means the Scenes produce nothing readable.
    taps = named + generic
    dims = {
        "outcomes_named": (named / taps if taps else 0) >= 0.1 and named >= 0.01 * vol,
        "screen_transitions": bool(swipes),
        "custom_events": bool(customs),
    }
    met = sum(1 for v in dims.values() if v)
    grade = ("blind" if met == 0 else "outcomes" if not dims["custom_events"]
             else "instrumented" if met == 3 else "partial")
    return {
        "volume": vol,
        "grade": grade,
        "dimensions": dims,
        "named_share": round(named / taps, 4) if taps else 0.0,
        "taps": taps,
        "named": named, "generic": generic, "swipes": swipes,
        "custom_events": sorted(set(customs))[:20],
        # What to fix, in the order it pays off. The step-level funnel is the one that needs
        # app work; the other two are configuration.
        "missing": [k for k, v in dims.items() if not v],
        "remediation": ([] if dims["custom_events"] else ["scene_custom_events"])
                       + ([] if dims["outcomes_named"] else ["name_the_buttons"]),
    }


def scene_instrumentation_from_audit(audit: Optional[dict]) -> dict:
    """The same grade, read from a built `audit.json` instead of the raw `/events` feed.

    Sections read the audit, not the collected feed, and asking each one to reconstruct
    event rows is how the same reconstruction ends up written five slightly different ways.
    Uses `inapp.top_ctas` for the interaction names and `events.taxonomy` for the account's
    own custom events.

    `top_ctas` is a TRUNCATED list, so the shares here are computed over the CTAs it does
    carry — the ranking is what matters for a grade, and the tail is small by construction.
    `volume` is taken from `inapp.interactions` where present so the figure the section
    prints matches the one the rest of the report uses.
    """
    a = audit or {}
    ia = a.get("inapp") or {}
    rows: List[dict] = [{"location": "in_app_pager", "name": str(name), "count": _int(cnt)}
                        for name, cnt in (ia.get("top_ctas") or [])]
    for t in ((a.get("events") or {}).get("taxonomy") or []):
        if not isinstance(t, dict):
            continue
        locs = [str(x).lower() for x in (t.get("locations") or [])]
        if "custom" in locs:
            rows.append({"location": "custom", "name": t.get("name") or "",
                         "count": _int(t.get("total"))})
    si = scene_instrumentation(rows)
    if si.get("volume") and _int(ia.get("interactions")):
        si["volume_ctas"] = si["volume"]
        si["volume"] = _int(ia["interactions"])
    return si


# The fix is the same every time, so it is written once here rather than re-argued per
# client. `scene_custom_events` is the one that unlocks a funnel; naming buttons only makes
# the existing events readable.
SCENE_REMEDIATION = {
    "scene_custom_events": (
        "Fire a custom event on Scene view and on Scene completion (or enable Scene event "
        "streaming), so abandonment can be located on a screen instead of inferred from a "
        "dismissal count.",
        "\u00c9mettre un \u00e9v\u00e9nement personnalis\u00e9 \u00e0 l'affichage et \u00e0 "
        "la compl\u00e9tion de la Scene (ou activer le streaming d'\u00e9v\u00e9nements de "
        "Scene), pour situer l'abandon sur un \u00e9cran au lieu de le d\u00e9duire d'un "
        "compte de fermetures."),
    "name_the_buttons": (
        "Give every Scene button an explicit identifier in the composer. Airship reports "
        "the identifier it is given, so a default `dismiss_button` costs the account the "
        "one thing the event could have said.",
        "Donner \u00e0 chaque bouton de Scene un identifiant explicite dans le composer. "
        "Airship remonte l'identifiant qu'on lui donne\u00a0: un `dismiss_button` par "
        "d\u00e9faut co\u00fbte la seule information que l'\u00e9v\u00e9nement pouvait "
        "porter."),
}


# ---- self-test --------------------------------------------------------------
if __name__ == "__main__":
    demo_events = [
        {"location": "custom", "name": "app_went_fidelite", "count": 100},
        {"location": "custom", "name": "banner - promo ciblée - coupons - j+10", "count": 2000},
        {"location": "in_app_message", "name": "button-click-Je m'inscris", "count": 64},
        {"location": "in_app_message", "name": "button-click-Je crée ma carte de fidélité", "count": 90},
        {"location": "in_app_pager", "name": "button-tap-next--clic_CTA_Onboarding_LEX_Suite", "count": 18803},
        {"location": "ua_mcrap", "name": "button_click:Assurance", "count": 500},
        {"location": "ua_mcrap", "name": "button_click:3f8a9b2c1d", "count": 999},  # uuid noise
    ]
    beh, inapp = split_events(demo_events)
    assert [e["name"] for e in beh] == ["app_went_fidelite"], beh
    assert len(inapp) == 6, len(inapp)
    inv = build_inventory(
        push_campaigns=[{"label": "Soldes été -30%", "type": "one_shot", "total_sends": 900000,
                         "channel": "push", "push_uuids": ["u1"]}],
        events=demo_events)
    labels = [c["label"] for c in inv["campaigns"]]
    assert any("inscris" in l.lower() for l in labels), labels
    assert any("carte de fidélité" in l.lower() for l in labels), labels
    assert not any(_looks_like_uuid(l.split("— ")[-1]) for l in labels), labels  # uuid dropped
    assert inv["stats"]["by_source"]["message"] == 1
    assert inv["stats"]["by_source"]["cta_only"] >= 4
    b = bucket_long_tail(inv["campaigns"], 500)
    assert b["tail_count"] >= 1

    # -- Scene instrumentation --
    # No in-app volume: §8b is a legitimate N/A, not a blind Scene.
    assert scene_instrumentation([{"location": "custom", "name": "x", "count": 9}])["volume"] == 0

    # A Scene nobody instrumented: every identifier is one Airship generated itself.
    blind = scene_instrumentation([
        {"location": "in_app_pager", "name": "user-dismissed", "count": 28903},
        {"location": "in_app_pager", "name": "button-tap-dismiss_button", "count": 28905},
        {"location": "in_app_message", "name": "message-click", "count": 7}])
    assert blind["grade"] == "blind", blind
    assert blind["missing"] == ["outcomes_named", "screen_transitions", "custom_events"]
    assert blind["remediation"] == ["scene_custom_events", "name_the_buttons"]

    # A property-listings shape: named buttons and pager swipes, no custom event on the flow
    # — the result is readable, the path through the screens is not.
    scenes = scene_instrumentation([
        {"location": "in_app_pager", "name": "button-tap-dismiss_button", "count": 28905},
        {"location": "in_app_pager", "name": "user-dismissed", "count": 28903},
        {"location": "in_app_pager", "name": "swipe-0-1", "count": 12098},
        {"location": "in_app_pager", "name": "swipe--1--1", "count": 193},
        {"location": "in_app_pager", "name": "button-tap-submit_feedback--Envoyer", "count": 3278},
        {"location": "in_app_pager", "name": "button-tap-clicked_inapp_csat_chat_5", "count": 2012},
        {"location": "in_app_pager", "name": "button-tap-push_opt_in--clicked_inapp_push-optin",
         "count": 65},
        {"location": "custom", "name": "onboarding_finished", "count": 4000}])
    assert scenes["grade"] == "outcomes", scenes
    assert scenes["dimensions"] == {"outcomes_named": True, "screen_transitions": True,
                                     "custom_events": False}, scenes["dimensions"]
    assert scenes["missing"] == ["custom_events"], scenes["missing"]
    # `onboarding_finished` must NOT count: it may be an app onboarding and not a Scene.
    assert scenes["custom_events"] == [], scenes["custom_events"]
    assert scenes["swipes"] == 12098 + 193

    # Explicit naming does count, and it is the dimension that unlocks the funnel.
    full = scene_instrumentation([
        {"location": "in_app_pager", "name": "swipe-0-1", "count": 10},
        {"location": "in_app_pager", "name": "button-tap-cta_estimate--Estimer", "count": 40},
        {"location": "custom", "name": "scene_onboarding_completed", "count": 900}])
    assert full["grade"] == "instrumented" and full["missing"] == [], full
    assert full["custom_events"] == ["scene_onboarding_completed"]

    # A named button that is a rounding error does not earn the dimension.
    thin = scene_instrumentation([
        {"location": "in_app_pager", "name": "user-dismissed", "count": 100_000},
        {"location": "in_app_pager", "name": "button-tap-deep_link--En savoir plus", "count": 3}])
    assert thin["dimensions"]["outcomes_named"] is False, thin["named_share"]

    for keys in (blind["remediation"], scenes["remediation"]):
        assert all(k in SCENE_REMEDIATION for k in keys), keys
    print("campaign_inventory self-test OK ·", inv["stats"], "· scenes:", scenes["grade"])
