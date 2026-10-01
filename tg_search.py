"""Поиск и проверка публичных групп через пользовательский аккаунт (Telethon)."""

MAX_FLOOD_WAIT = 90   # если Telegram просит ждать дольше — останавливаем поиск
MSG_SAMPLE = 100      # сколько последних сообщений анализировать


class StopSearch(Exception):
    pass


async def tg_call(factory, retries=3, timeout=30):
    import asyncio
    from telethon import errors

    last = None
    for attempt in range(retries):
        try:
            return await asyncio.wait_for(factory(), timeout)
        except errors.FloodWaitError as e:
            if e.seconds > MAX_FLOOD_WAIT:
                raise
            await asyncio.sleep(e.seconds + 1)
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            last = e
            await asyncio.sleep(2 ** attempt)
    raise last or RuntimeError("Не удалось выполнить запрос к Telegram")


async def load_group_info(client, chat, pid, now):
    from telethon import functions
    from group_filters import analyze_messages

    full = await tg_call(lambda: client(functions.channels.GetFullChannelRequest(chat)))
    fc = full.full_chat
    msgs = await tg_call(lambda: client.get_messages(chat, limit=MSG_SAMPLE))
    from storage import get_settings
    window = get_settings()["window_hours"]
    return {
        "id": pid,
        "title": chat.title or "",
        "username": chat.username,
        "members": getattr(fc, "participants_count", None) or getattr(chat, "participants_count", 0) or 0,
        "about": fc.about or "",
        "date": chat.date,
        "analysis": analyze_messages(msgs, now, window),
    }


def _bump(stats, reason):
    stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1


async def collect_groups(client, queries, limit, settings, progress, stop_event, found_ids):
    """Возвращает (results, stats). found_ids — set, пополняется и сохраняется на диск."""
    import asyncio
    import logging
    import random
    from datetime import datetime, timezone
    from telethon import errors, functions, utils
    from group_filters import quick_check, deep_check
    from storage import save_found_ids

    log = logging.getLogger("tgbot.search")
    results, seen = [], set()
    stats = {"checked": 0, "duplicates": 0, "queries_done": 0, "reasons": {}, "stopped": None}

    try:
        for q in queries:
            if len(results) >= limit or stop_event.is_set():
                break
            try:
                res = await tg_call(lambda: client(functions.contacts.SearchRequest(q=q, limit=100)))
            except errors.FloodWaitError as e:
                stats["stopped"] = f"Telegram просит подождать {e.seconds} сек (FloodWait)"
                raise StopSearch()
            except errors.RPCError as e:
                log.warning("search '%s' failed: %s", q, e)
                continue
            stats["queries_done"] += 1
            await progress(f"🔎 Запрос «{q}»: найдено {len(res.chats)} чатов\n"
                           f"✅ Подходящих: {len(results)}/{limit} | проверено: {stats['checked']}")

            for chat in res.chats:
                if len(results) >= limit or stop_event.is_set():
                    break
                try:
                    pid = utils.get_peer_id(chat)
                except Exception:
                    continue
                if pid in seen:
                    continue
                seen.add(pid)
                if pid in found_ids:
                    stats["duplicates"] += 1
                    continue

                now = datetime.now(timezone.utc)
                reason = quick_check(chat, settings, now)
                if reason:
                    _bump(stats, reason)
                    continue

                stats["checked"] += 1
                await asyncio.sleep(settings["delay"] + random.random())
                try:
                    info = await load_group_info(client, chat, pid, now)
                except errors.FloodWaitError as e:
                    stats["stopped"] = f"Telegram просит подождать {e.seconds} сек (FloodWait)"
                    raise StopSearch()
                except errors.RPCError as e:
                    _bump(stats, "no_access")
                    log.info("skip %s: %s", pid, e)
                    continue
                except (asyncio.TimeoutError, ConnectionError, OSError):
                    _bump(stats, "network_error")
                    continue

                reason = deep_check(info, settings, now)
                if reason:
                    _bump(stats, reason)
                else:
                    results.append(info)
                    found_ids.add(pid)
                    save_found_ids(found_ids)
                    await progress(f"✅ Подходящих: {len(results)}/{limit} | проверено: {stats['checked']}\n"
                                   f"Последняя: {info['title'][:40]}")
                if stats["checked"] % 10 == 0:
                    await progress(f"✅ Подходящих: {len(results)}/{limit} | проверено: {stats['checked']}")
    except StopSearch:
        pass
    return results, stats


def write_result_file(results):
    from storage import path
    p = path("result_groups.txt")
    with open(p, "w", encoding="utf-8") as f:
        for g in results:
            f.write("---\n")
            f.write(f"Название группы: {g['title']}\n")
            f.write(f"Ссылка: https://t.me/{g['username']}\n")
            f.write(f"ID: {g['id']}\n")
            f.write("---\n\n")
    return p
