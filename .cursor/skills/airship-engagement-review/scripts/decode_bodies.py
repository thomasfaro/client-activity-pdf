#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decode the `pushbody` caches into structured creatives — no network, no Content API.

`GET /api/reports/perpush/pushbody/{id}` returns the push payload base64-encoded. Three
wrapping quirks make a naive decode return empty creatives on real accounts, and each one
was found the hard way on a shipped review:

  1. **Double wrapping.** A scheduled push is `{"schedule": …, "push": {…}}` (and `push`
     may itself be a list), not the push object directly.
  2. **Message templates.** The copy often sits under
     `notification.<platform>.template.fields.{title,alert}` instead of
     `notification.<platform>.alert` — every marquee broadcast on a streaming account
     decodes empty without this.
  3. **Handlebars multi-language.** Copy can be one string carrying every locale
     (`{{#eq ua_language "fr"}}…{{else}}…`). Rendering it raw shows template syntax to
     the client, so a locale is selected and the remaining tags are stripped.

Group payloads (`group_id`) decode to one of two shapes: an **automation/journey
definition** (`immediate_trigger` + `outcome.push`) or a **scheduled broadcast**
(`schedule` + `push`) — the latter is how local-time and best-time (STO) delivery appear.

Pure stdlib. Entry points: `decode_pushbodies(cache)`, `decode_groupbodies(cache, pergroup)`.
"""

import base64
import json
import re

# {{#eq ua_language "xx"}}<copy>{{else}} — the per-locale branch of a templated string
_LANG_BRANCH = '{{#eq ua_language "%s"}}'
_HANDLEBARS = re.compile(r"\{\{/?[#^]?\w[^}]*\}\}")
_LANG_DECL = re.compile(r'ua_language \\?"([a-z]{2})\\?"')


def b64(s):
    """Decode a base64 push_body (padding-tolerant, url-safe or standard)."""
    if not s:
        return None
    s = s + "=" * (-len(s) % 4)
    for dec in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return json.loads(dec(s.encode()).decode("utf-8"))
        except Exception:  # noqa: BLE001 — try the next codec, then give up
            continue
    return None


def pick_locale(txt, lang="fr"):
    """Return one locale's copy from a handlebars multi-language string."""
    if not isinstance(txt, str):
        return None if txt is None else str(txt)
    head = _LANG_BRANCH % lang
    i = txt.find(head)
    if i >= 0:
        rest = txt[i + len(head):]
        end = rest.find("{{else")
        txt = rest[:end] if end >= 0 else rest
    txt = _HANDLEBARS.sub("", txt)
    return txt.replace("\\n", " ").replace("\n", " ").strip()


def unwrap(body):
    """`{"schedule":…,"push":{…}}` -> (push_payload, scheduled_time)."""
    sched = None
    if isinstance(body, dict) and "push" in body:
        s = body.get("schedule")
        sched = s.get("scheduled_time") if isinstance(s, dict) else None
        p = body["push"]
        body = p[0] if isinstance(p, list) and p else p
    return (body if isinstance(body, dict) else {}), sched


def flatten_platform(plat):
    """Platform block with `template.fields` folded in (template copy wins nothing —
    it only fills what the platform block left unset)."""
    if not isinstance(plat, dict):
        return {}
    out = dict(plat)
    tpl = plat.get("template")
    fields = tpl.get("fields") if isinstance(tpl, dict) else None
    if isinstance(fields, dict):
        for k, v in fields.items():
            out.setdefault(k, v)
    return out


def read_push(push, lang="fr"):
    """Common creative extraction shared by per-push and per-group payloads."""
    if isinstance(push, list):
        push = push[0] if push else {}
    if not isinstance(push, dict):
        return {}
    notif = push.get("notification") or {}
    ios = flatten_platform(notif.get("ios"))
    android = flatten_platform(notif.get("android"))
    web = flatten_platform(notif.get("web"))

    alert = ios.get("alert")
    title = ((alert.get("title") if isinstance(alert, dict) else None)
             or ios.get("title") or android.get("title") or web.get("title"))
    body = ((alert.get("body") if isinstance(alert, dict) else alert)
            or android.get("alert") or web.get("alert") or notif.get("alert"))

    media_ios = ios.get("media_attachment")
    style = android.get("style")
    media = ((media_ios.get("url") if isinstance(media_ios, dict) else None)
             or (style.get("big_picture") if isinstance(style, dict) else None)
             or android.get("image") or ios.get("image"))

    actions = {}
    for plat in (ios, android, web, notif):
        a = plat.get("actions") if isinstance(plat, dict) else None
        if isinstance(a, dict):
            actions.update(a)
    op = actions.get("open")

    opts = push.get("options") or {}
    raw = json.dumps(push, ensure_ascii=False)
    return {
        "title": pick_locale(title, lang), "body": pick_locale(body, lang),
        "title_raw": title, "body_raw": body,
        "media": media,
        "deeplink": op.get("content") if isinstance(op, dict) else None,
        "add_tags": actions.get("add_tag") or [],
        "device_types": push.get("device_types"),
        "audience": push.get("audience") if isinstance(push.get("audience"), (str, dict)) else None,
        "languages": sorted(set(_LANG_DECL.findall(raw))),
        "personalization": bool(opts.get("personalization")) or "{{" in raw,
        "ui_id": opts.get("__ui_id"),
        "message_name": opts.get("message_name"),
        "bypass_frequency_limits": bool(opts.get("bypass_frequency_limits")),
        "has_message_center": bool(push.get("message")),
        "mc_title": (push.get("message") or {}).get("title") if push.get("message") else None,
        "mc_html": (push.get("message") or {}).get("body") if push.get("message") else None,
        "in_app": bool(push.get("in_app")),
    }


def decode_pushbodies(cache, lang="fr"):
    """`{push_id: {"push_body": b64}}` -> `{push_id: {...creative...}}`."""
    out = {}
    for pid, raw in (cache or {}).items():
        if not isinstance(raw, dict) or raw.get("_error"):
            continue
        decoded = b64(raw.get("push_body"))
        if decoded is None:
            out[pid] = {"decodable": False}
            continue
        push, sched = unwrap(decoded)
        rec = read_push(push, lang)
        camp = push.get("campaigns") or {}
        aud = rec.get("audience")
        raw_text = json.dumps(decoded, ensure_ascii=False)
        rec.update({
            "decodable": True,
            "message_name": rec.get("message_name") or camp.get("name"),
            "categories": camp.get("categories"),
            "templated": "template" in json.dumps(push.get("notification") or {})[:100000],
            "scheduled": sched,
            "audience_kind": ("segment" if "segment" in raw_text
                              else "tag" if isinstance(aud, dict) and "tag" in aud
                              else "all" if aud == "all" else "other"),
        })
        out[pid] = rec
    return out


def _triggers(trigger):
    """Normalize an automation's `immediate_trigger` into readable trigger names."""
    out = []
    for item in (trigger if isinstance(trigger, list) else [trigger]):
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            for k, v in item.items():
                if k == "pipeline_event" and isinstance(v, dict):
                    out.append(f"pipeline:{v.get('type')}")
                elif k == "segmentation_result":
                    out.append("segment_entry")
                else:
                    out.append(k)
    return out


def decode_groupbodies(cache, pergroup=None, lang="fr"):
    """`{group_id: {"push_body": b64}}` + pergroup/detail -> program records."""
    pergroup = pergroup or {}
    out = {}
    for gid, raw in (cache or {}).items():
        meta = pergroup.get(gid) or {}
        rec = {
            "group_id": gid,
            "lifetime_sends": meta.get("sends"),
            "lifetime_direct": meta.get("direct_responses"),
            "lifetime_influenced": meta.get("influenced_responses"),
            "platforms": meta.get("platforms"),
            "window_sends": meta.get("_sends_responses"),
            "occurrences": meta.get("_occurrences"),
            "first": meta.get("_first"), "last": meta.get("_last"),
            "app_key": meta.get("app_key"),
        }
        dec = b64((raw or {}).get("push_body")) if isinstance(raw, dict) else None
        if not isinstance(dec, dict):
            rec["kind"] = "undecodable"
            out[gid] = rec
            continue
        if "outcome" in dec or "immediate_trigger" in dec:
            rec.update(read_push((dec.get("outcome") or {}).get("push") or {}, lang))
            rec.update({
                "kind": "automation",
                "name": dec.get("name"),
                "status": dec.get("status"),
                "enabled": dec.get("enabled"),
                "created": dec.get("creation_time"),
                "modified": dec.get("last_modified_time"),
                "triggers": _triggers(dec.get("immediate_trigger")),
                "conditions": bool(dec.get("condition") or dec.get("conditions")),
                "delay": (dec.get("outcome") or {}).get("delay") or dec.get("delay"),
            })
        else:
            sched = dec.get("schedule") or {}
            rec.update(read_push(dec.get("push") or dec, lang))
            rec.update({
                "kind": "scheduled_broadcast",
                "name": rec.get("message_name"),
                "best_time": bool(sched.get("best_time")),
                "local_time": bool(sched.get("local_scheduled_time")),
                "scheduled": ((sched.get("best_time") or {}).get("send_date")
                              or sched.get("local_scheduled_time")
                              or sched.get("scheduled_time")),
            })
        out[gid] = rec
    return out


def summarise(decoded):
    """Feature counts for the adoption scorecard and the collection manifest."""
    dec = [v for v in decoded.values() if v.get("decodable")]
    return {
        "bodies": len(decoded),
        "decodable": len(dec),
        "with_copy": sum(1 for v in dec if v.get("title") or v.get("body")),
        "hero_image": sum(1 for v in dec if v.get("media")),
        "deeplink": sum(1 for v in dec if v.get("deeplink")),
        "personalized": sum(1 for v in dec if v.get("personalization")),
        "multilingual": sum(1 for v in dec if v.get("languages")),
        "message_center": sum(1 for v in dec if v.get("has_message_center")),
        "composer_id": sum(1 for v in dec if v.get("ui_id")),
        "named": sum(1 for v in dec if v.get("message_name")),
    }


if __name__ == "__main__":
    import os
    import sys

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    d = sys.argv[1]
    pb = json.load(open(os.path.join(d, "pushbodies.json"), encoding="utf-8"))
    out = decode_pushbodies(pb)
    json.dump(out, open(os.path.join(d, "decoded.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(" · ".join(f"{k}={v}" for k, v in summarise(out).items()))
    gpath = os.path.join(d, "groupbodies.json")
    if os.path.isfile(gpath):
        ppath = os.path.join(d, "pergroup.json")
        pg = json.load(open(ppath, encoding="utf-8")) if os.path.isfile(ppath) else {}
        gd = decode_groupbodies(json.load(open(gpath, encoding="utf-8")), pg)
        json.dump(gd, open(os.path.join(d, "groups_decoded.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        kinds = {}
        for v in gd.values():
            kinds[v.get("kind")] = kinds.get(v.get("kind"), 0) + 1
        print("groups:", kinds)
