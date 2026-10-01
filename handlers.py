"""Обработчики aiogram: меню, подключение аккаунта, поиск, настройки."""

STATE = {}      # user_id -> {"step": ..., ...}
PENDING = {}    # user_id -> {"topic": ..., "queries": [...]}
RUNTIME = {"task": None, "stop": None}


# ---------- вспомогательное ----------
def _kb(rows):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows
    ])


def menu_kb():
    return _kb([
        [("🔍 Найти группы", "find")],
        [("🔐 Аккаунт", "acc"), ("⚙️ Настройки", "settings")],
        [("🗑 Сбросить список найденных", "reset_found")],
    ])


def _allowed(user_id, claim=False):
    from storage import get_owner, set_owner
    owner = get_owner()
    if owner is None:
        if claim:
            set_owner(user_id)
            return True
        return False
    return owner == user_id


async def _delete_quiet(message):
    try:
        await message.delete()
    except Exception:
        pass


def settings_text(s):
    from storage import SETTINGS_META
    lines = ["⚙️ Текущие настройки:\n"]
    for key, (label, _) in SETTINGS_META.items():
        v = s.get(key)
        if isinstance(v, list):
            v = ", ".join(v) or "—"
        lines.append(f"• {label}: {v}")
    return "\n".join(lines)


def settings_kb():
    from storage import SETTINGS_META
    items = [(label, f"set:{key}") for key, (label, _) in SETTINGS_META.items()]
    rows = [items[i:i + 2] for i in range(0, len(items), 2)]
    rows.append([("⬅️ Меню", "menu")])
    return _kb(rows)


def parse_value(kind, text):
    import re
    if kind == "int":
        v = int(text)
        if v < 0:
            raise ValueError
        return v
    if kind == "float":
        v = float(text.replace(",", "."))
        if v < 0:
            raise ValueError
        return v
    if kind == "list":
        if text.strip() in ("-", "0"):
            return []
        return [w.strip().lower() for w in re.split(r"[,\n;]+", text) if w.strip()]
    raise ValueError


def parse_query_list(text):
    import re
    items, seen = [], set()
    for w in re.split(r"[,\n;]+", text):
        w = w.strip()
        if 2 <= len(w) <= 64 and w.lower() not in seen:
            seen.add(w.lower())
            items.append(w)
    return items[:30]


# ---------- команды ----------
async def cmd_start(message):
    uid = message.from_user.id
    if not _allowed(uid, claim=True):
        await message.answer("⛔ Доступ запрещён.")
        return
    STATE.pop(uid, None)
    await message.answer(
        "👋 Привет! Я помогаю искать качественные публичные группы Telegram.\n\n"
        "1) Подключите аккаунт (🔐)\n2) Настройте фильтры (⚙️)\n3) Нажмите «Найти группы»",
        reply_markup=menu_kb(),
    )


async def cmd_cancel(message):
    if not _allowed(message.from_user.id):
        return
    STATE.pop(message.from_user.id, None)
    await message.answer("Отменено.", reply_markup=menu_kb())


# ---------- inline-кнопки ----------
async def on_callback(cb):
    uid = cb.from_user.id
    if not _allowed(uid):
        await cb.answer("Нет доступа", show_alert=True)
        return
    data = cb.data or ""
    await cb.answer()
    msg = cb.message

    if data == "menu":
        STATE.pop(uid, None)
        await msg.answer("Главное меню:", reply_markup=menu_kb())

    elif data == "acc":
        await show_account(msg)
    elif data == "acc_new":
        STATE[uid] = {"step": "api_id"}
        await msg.answer("Введите API ID (получить: my.telegram.org → API development tools).\n/cancel — отмена")
    elif data == "acc_logout":
        from account import logout
        await logout()
        await msg.answer("Аккаунт отключён, сессия удалена.", reply_markup=menu_kb())

    elif data == "find":
        await begin_find(msg, uid)
    elif data == "q_ok":
        await msg.answer("Сколько групп максимум найти?", reply_markup=_kb([
            [("20", "lim:20"), ("50", "lim:50"), ("100", "lim:100")],
            [("Своё число", "lim:custom")],
        ]))
    elif data == "q_edit":
        STATE[uid] = {"step": "queries_edit"}
        await msg.answer("Отправьте свой список запросов (через запятую или с новой строки, до 30):")
    elif data.startswith("lim:"):
        val = data.split(":", 1)[1]
        if val == "custom":
            STATE[uid] = {"step": "limit_custom"}
            await msg.answer("Введите число (1–500):")
        else:
            await start_search(msg.bot, msg.chat.id, uid, int(val))
    elif data == "stop":
        if RUNTIME["stop"]:
            RUNTIME["stop"].set()
        await msg.answer("⏳ Останавливаю, подождите завершения текущей проверки...")

    elif data == "settings":
        from storage import get_settings
        await msg.answer(settings_text(get_settings()), reply_markup=settings_kb())
    elif data == "set:language":
        await msg.answer("Предпочтительный язык групп:", reply_markup=_kb([
            [("Русский", "lang:ru"), ("Українська", "lang:uk")],
            [("English", "lang:en"), ("Любой", "lang:any")],
        ]))
    elif data.startswith("lang:"):
        from storage import update_setting, get_settings
        update_setting("language", data.split(":", 1)[1])
        await msg.answer("✅ Сохранено.\n\n" + settings_text(get_settings()), reply_markup=settings_kb())
    elif data.startswith("set:"):
        from storage import SETTINGS_META
        key = data.split(":", 1)[1]
        if key in SETTINGS_META:
            STATE[uid] = {"step": "setting", "key": key}
            hint = " (для очистки отправьте «-»)" if SETTINGS_META[key][1] == "list" else ""
            await msg.answer(f"Введите новое значение: {SETTINGS_META[key][0]}{hint}")

    elif data == "reset_found":
        await msg.answer("Удалить список уже найденных групп? Они снова смогут попасть в выдачу.",
                         reply_markup=_kb([[("Да, удалить", "reset_yes"), ("Нет", "menu")]]))
    elif data == "reset_yes":
        from storage import save_found_ids
        save_found_ids(set())
        await msg.answer("Список очищен.", reply_markup=menu_kb())


async def show_account(msg):
    from account import get_client
    client = await get_client()
    if client:
        try:
            me = await client.get_me()
            who = f"{me.first_name or ''} (@{me.username})" if me.username else (me.first_name or str(me.id))
        except Exception:
            who = "аккаунт"
        await msg.answer(f"✅ Подключён: {who}", reply_markup=_kb([
            [("🔄 Подключить другой", "acc_new"), ("🚪 Отключить", "acc_logout")],
            [("⬅️ Меню", "menu")],
        ]))
    else:
        await msg.answer("Аккаунт не подключён.", reply_markup=_kb([
            [("🔐 Подключить", "acc_new")], [("⬅️ Меню", "menu")],
        ]))


async def begin_find(msg, uid):
    from account import get_client
    if RUNTIME["task"] and not RUNTIME["task"].done():
        await msg.answer("Поиск уже выполняется.", reply_markup=_kb([[("⛔ Остановить", "stop")]]))
        return
    if not await get_client():
        await msg.answer("Сначала подключите аккаунт.", reply_markup=_kb([[("🔐 Подключить", "acc_new")]]))
        return
    STATE[uid] = {"step": "topic"}
    await msg.answer("Введите тематику для поиска (например: заработок):")


# ---------- текстовые сообщения ----------
async def on_text(message):
    uid = message.from_user.id
    if not _allowed(uid):
        return
    st = STATE.get(uid)
    if not st:
        await message.answer("Нажмите /start, чтобы открыть меню.")
        return
    step = st["step"]
    text = (message.text or "").strip()

    if step == "api_id":
        if not text.isdigit():
            await message.answer("API ID — это число. Попробуйте ещё раз:")
            return
        await _delete_quiet(message)
        st.update(step="api_hash", api_id=int(text))
        await message.answer("Теперь введите API Hash:")

    elif step == "api_hash":
        await _delete_quiet(message)
        if len(text) < 20:
            await message.answer("Похоже на неверный API Hash. Попробуйте ещё раз:")
            return
        st.update(step="phone", api_hash=text)
        await message.answer("Введите номер телефона в международном формате (+49...):")

    elif step == "phone":
        import re
        from account import begin_login
        await _delete_quiet(message)
        phone = "+" + re.sub(r"\D", "", text)
        try:
            st["login"] = await begin_login(st["api_id"], st["api_hash"], phone)
        except Exception as e:
            STATE.pop(uid, None)
            await message.answer(f"❌ Не удалось отправить код: {type(e).__name__}\n"
                                 f"Проверьте API ID/Hash и номер, затем начните заново.", reply_markup=menu_kb())
            return
        st["step"] = "code"
        await message.answer(
            "📩 Код отправлен в Telegram. Введите его, разделив цифры тире или пробелами "
            "(например 1-2-3-4-5) — иначе Telegram может аннулировать код, отправленный в чат.")

    elif step == "code":
        import re
        from telethon import errors
        from account import finish_login, abort_login
        await _delete_quiet(message)
        code = re.sub(r"\D", "", text)
        try:
            res = await finish_login(st["login"], code=code)
        except errors.PhoneCodeInvalidError:
            await message.answer("Неверный код. Попробуйте ещё раз:")
            return
        except errors.PhoneCodeExpiredError:
            await abort_login(st["login"])
            STATE.pop(uid, None)
            await message.answer("Код истёк. Начните подключение заново.", reply_markup=menu_kb())
            return
        except Exception as e:
            await abort_login(st["login"])
            STATE.pop(uid, None)
            await message.answer(f"❌ Ошибка входа: {type(e).__name__}", reply_markup=menu_kb())
            return
        if res == "password":
            st["step"] = "password"
            await message.answer("🔑 Включена двухфакторная защита. Введите пароль:")
        else:
            STATE.pop(uid, None)
            await message.answer("✅ Аккаунт подключён!", reply_markup=menu_kb())

    elif step == "password":
        from telethon import errors
        from account import finish_login, abort_login
        await _delete_quiet(message)
        try:
            await finish_login(st["login"], password=text)
        except errors.PasswordHashInvalidError:
            await message.answer("Неверный пароль. Попробуйте ещё раз:")
            return
        except Exception as e:
            await abort_login(st["login"])
            STATE.pop(uid, None)
            await message.answer(f"❌ Ошибка входа: {type(e).__name__}", reply_markup=menu_kb())
            return
        STATE.pop(uid, None)
        await message.answer("✅ Аккаунт подключён!", reply_markup=menu_kb())

    elif step == "topic":
        from llm import generate_queries, LLMError
        from storage import get_settings
        wait = await message.answer("⏳ Генерирую поисковые запросы через ИИ...")
        try:
            queries = await generate_queries(text, get_settings()["language"])
        except LLMError as e:
            await _delete_quiet(wait)
            PENDING[uid] = {"topic": text, "queries": [text]}
            st["step"] = "queries_edit"
            await message.answer(f"⚠️ LLM недоступен ({e}).\nОтправьте список запросов вручную "
                                 f"(через запятую или с новой строки):")
            return
        await _delete_quiet(wait)
        PENDING[uid] = {"topic": text, "queries": queries}
        st["step"] = "confirm"
        await _show_queries(message, queries)

    elif step == "queries_edit":
        queries = parse_query_list(text)
        if not queries:
            await message.answer("Не нашёл запросов. Отправьте список ещё раз:")
            return
        PENDING.setdefault(uid, {"topic": ""})["queries"] = queries
        st["step"] = "confirm"
        await _show_queries(message, queries)

    elif step == "limit_custom":
        if not text.isdigit() or not (1 <= int(text) <= 500):
            await message.answer("Введите число от 1 до 500:")
            return
        STATE.pop(uid, None)
        await start_search(message.bot, message.chat.id, uid, int(text))

    elif step == "setting":
        from storage import SETTINGS_META, update_setting, get_settings
        key = st["key"]
        try:
            value = parse_value(SETTINGS_META[key][1], text)
        except ValueError:
            await message.answer("Неверный формат значения. Попробуйте ещё раз:")
            return
        update_setting(key, value)
        STATE.pop(uid, None)
        await message.answer("✅ Сохранено.\n\n" + settings_text(get_settings()), reply_markup=settings_kb())


async def _show_queries(message, queries):
    listing = "\n".join(f"• {q}" for q in queries)
    await message.answer(f"🧠 Поисковые запросы:\n\n{listing}\n\nИспользовать эти запросы для поиска?",
                         reply_markup=_kb([[("✅ Да", "q_ok"), ("✏️ Свой список", "q_edit")],
                                           [("❌ Отмена", "menu")]]))


# ---------- запуск поиска ----------
async def start_search(bot, chat_id, uid, limit):
    import asyncio
    if RUNTIME["task"] and not RUNTIME["task"].done():
        await bot.send_message(chat_id, "Поиск уже выполняется.")
        return
    if not PENDING.get(uid, {}).get("queries"):
        await bot.send_message(chat_id, "Нет списка запросов. Начните с «Найти группы».", reply_markup=menu_kb())
        return
    RUNTIME["stop"] = asyncio.Event()
    RUNTIME["task"] = asyncio.create_task(run_search(bot, chat_id, uid, limit, RUNTIME["stop"]))


async def run_search(bot, chat_id, uid, limit, stop):
    import logging
    from aiogram.types import FSInputFile
    from account import get_client
    from storage import get_settings, load_found_ids
    from tg_search import collect_groups, write_result_file

    log = logging.getLogger("tgbot")
    stop_kb = _kb([[("⛔ Остановить", "stop")]])
    status = await bot.send_message(chat_id, "🔎 Поиск запущен...", reply_markup=stop_kb)
    last = {"text": ""}

    async def progress(text):
        if text == last["text"]:
            return
        last["text"] = text
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=status.message_id, reply_markup=stop_kb)
        except Exception:
            pass

    try:
        client = await get_client()
        if not client:
            await bot.send_message(chat_id, "Аккаунт не подключён или сессия недействительна.", reply_markup=menu_kb())
            return
        results, stats = await collect_groups(
            client, PENDING[uid]["queries"], limit, get_settings(), progress, stop, load_found_ids())
    except Exception as e:
        log.exception("search failed")
        await bot.send_message(chat_id, f"❌ Ошибка поиска: {type(e).__name__}: {e}\n"
                                        f"(возможно, аккаунт ограничен или сессия отозвана)", reply_markup=menu_kb())
        return
    finally:
        RUNTIME["task"] = None

    reasons = sorted(stats["reasons"].items(), key=lambda x: -x[1])[:6]
    rtxt = "\n".join(f"  – {k}: {v}" for k, v in reasons) or "  –"
    summary = (f"🏁 Готово. Найдено: {len(results)}/{limit}\n"
               f"Запросов выполнено: {stats['queries_done']}, глубоко проверено: {stats['checked']}, "
               f"уже было в базе: {stats['duplicates']}\nОтсев по причинам:\n{rtxt}")
    if stats["stopped"]:
        summary += f"\n⚠️ Остановлено: {stats['stopped']}"
    elif stop.is_set():
        summary += "\n⛔ Остановлено пользователем"
    await bot.send_message(chat_id, summary)

    if results:
        p = write_result_file(results)
        await bot.send_document(chat_id, FSInputFile(p, filename="result_groups.txt"),
                                caption=f"Найдено групп: {len(results)}", reply_markup=menu_kb())
    else:
        await bot.send_message(chat_id, "Ничего не найдено. Попробуйте смягчить фильтры в ⚙️ Настройках.",
                               reply_markup=menu_kb())


def build_router():
    from aiogram import Router, F
    from aiogram.filters import Command
    r = Router()
    r.message.register(cmd_start, Command("start", "menu"))
    r.message.register(cmd_cancel, Command("cancel"))
    r.callback_query.register(on_callback)
    r.message.register(on_text, F.text)
    return r
