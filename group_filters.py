"""Чистые функции фильтрации групп (без сетевых вызовов)."""

LINK_RATIO_MAX = 0.35
BOT_RATIO_MAX = 0.5
DUP_RATIO_MAX = 0.3
SHORT_RATIO_MAX = 0.6

def age_days(dt, now):
    from datetime import timezone
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days

def has_stop_word(text, stop_words):
    low = (text or "").lower()
    return any(w and w in low for w in stop_words)

def detect_language(text):
    cyr = lat = uk = ru_only = 0
    for ch in text.lower():
        if "а" <= ch <= "я" or ch in "ёіїєґ":
            cyr += 1
            if ch in "іїєґ":
                uk += 1
            elif ch in "ыэъё":
                ru_only += 1
        elif "a" <= ch <= "z":
            lat += 1
    total = cyr + lat
    if total < 15:
        return None
    if cyr / total > 0.5:
        return "uk" if uk > ru_only else "ru"
    if lat / total > 0.5:
        return "en"
    return None

def analyze_messages(messages, now, window_hours):
    import re
    from collections import Counter

    link_re = re.compile(r"(https?://|t\.me/|www\.|@\w{4,})", re.I)
    cutoff = window_hours * 3600
    total = recent = links = short = bots = 0
    senders, texts, counter = set(), [], Counter()

    for m in messages:
        if getattr(m, "action", None) is not None:
            continue
        total += 1
        if m.date and (now - m.date).total_seconds() <= cutoff:
            recent += 1
        if m.sender_id is not None:
            senders.add(m.sender_id)
        if getattr(getattr(m, "sender", None), "bot", False):
            bots += 1
        text = (m.message or "").strip()
        if text:
            texts.append(text)
            if len(text) >= 10:
                counter[text.lower()] += 1
            if link_re.search(text) and len(link_re.sub("", text).strip()) < 20:
                links += 1
            if len(text) < 3:
                short += 1

    dup = sum(c for c in counter.values() if c > 1)
    t = max(total, 1)
    return {
        "total": total,
        "recent": recent,
        "unique_senders": len(senders),
        "link_ratio": links / t,
        "bot_ratio": bots / t,
        "dup_ratio": dup / t,
        "short_ratio": short / t,
        "texts": texts,
    }

def is_spammy(a):
    return (
        a["link_ratio"] > LINK_RATIO_MAX
        or a["bot_ratio"] > BOT_RATIO_MAX
        or a["dup_ratio"] > DUP_RATIO_MAX
        or a["short_ratio"] > SHORT_RATIO_MAX
    )

def quick_check(chat, settings, now):
    from telethon.tl.types import Channel

    # Базовые проверки Telegram (что это супергруппа и она публичная)
    if not isinstance(chat, Channel): return "not_channel_type"
    if chat.broadcast or not chat.megagroup: return "not_group"
    if not chat.username: return "not_public"

    # Если фильтры отключены пользователем — пропускаем группу дальше
    if not settings.get("use_filters", True):
        return None

    if getattr(chat, "scam", False) or getattr(chat, "fake", False): return "scam_or_fake"
    if getattr(chat, "restricted", False): return "restricted"
    if getattr(chat, "join_request", False): return "join_request"
    
    members = getattr(chat, "participants_count", None)
    if members is not None and members < settings["min_members"]: return "few_members"
    
    age = age_days(chat.date, now)
    if age is not None and age < settings["min_age_days"]: return "too_new"
    if has_stop_word(chat.title, settings["stop_words"]): return "stop_word"
    
    return None

def deep_check(info, settings, now):
    if not settings.get("use_filters", True):
        return None

    if info["members"] < settings["min_members"]: return "few_members"
    about = (info["about"] or "").strip()
    if len(about) < settings["min_desc_len"]: return "short_description"

    a = info["analysis"]
    blob = " ".join([info["title"], about] + a["texts"])
    if has_stop_word(blob, settings["stop_words"]): return "stop_word"
    if a["recent"] < settings["min_msgs"]: return "low_activity"
    if a["unique_senders"] < settings["min_unique_senders"]: return "few_authors"
    if is_spammy(a): return "spam"

    age = age_days(info["date"], now)
    if age is not None:
        if age < settings["min_age_days"]: return "too_new"
        if age > settings.get("max_age_days", 3650) and a["recent"] < settings["min_msgs"] * 3:
            return "old_inactive"

    want = settings["language"]
    if want != "any":
        lang = detect_language((info["title"] + " " + about + " " + " ".join(a["texts"][:40]))[:5000])
        if lang is not None and lang != want:
            return "wrong_language"
            
    return None
