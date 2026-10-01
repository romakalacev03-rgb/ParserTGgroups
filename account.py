"""Управление пользовательской сессией Telethon."""

_STATE = {"client": None}


def _new_client(api_id, api_hash):
    from telethon import TelegramClient
    from storage import path
    # receive_updates=False — не принимаем апдейты: экономит CPU/RAM на бесплатном хостинге
    return TelegramClient(path("user"), int(api_id), api_hash, receive_updates=False,
                          device_model="Group Parser", app_version="1.0")


async def get_client():
    """Возвращает подключённый и авторизованный клиент либо None."""
    from storage import load_account
    c = _STATE["client"]
    try:
        if c is not None:
            if not c.is_connected():
                await c.connect()
            if await c.is_user_authorized():
                return c
    except Exception:
        _STATE["client"] = None
    acc = load_account()
    if not acc:
        return None
    try:
        c = _new_client(acc["api_id"], acc["api_hash"])
        await c.connect()
        if await c.is_user_authorized():
            _STATE["client"] = c
            return c
        await c.disconnect()
    except Exception:
        pass
    return None


async def begin_login(api_id, api_hash, phone):
    await logout(keep_files=True)
    client = _new_client(api_id, api_hash)
    await client.connect()
    sent = await client.send_code_request(phone)
    return {"client": client, "phone": phone, "hash": sent.phone_code_hash,
            "api_id": api_id, "api_hash": api_hash}


async def finish_login(login, code=None, password=None):
    """Возвращает 'ok' или 'password' (нужен пароль 2FA)."""
    from telethon.errors import SessionPasswordNeededError
    from storage import save_account
    client = login["client"]
    if password is not None:
        await client.sign_in(password=password)
    else:
        try:
            await client.sign_in(phone=login["phone"], code=code, phone_code_hash=login["hash"])
        except SessionPasswordNeededError:
            return "password"
    save_account(login["api_id"], login["api_hash"])
    _STATE["client"] = client
    return "ok"


async def abort_login(login):
    try:
        await login["client"].disconnect()
    except Exception:
        pass


async def logout(keep_files=False):
    from storage import delete_account
    c = _STATE["client"]
    _STATE["client"] = None
    if c is not None:
        try:
            if not keep_files:
                await c.log_out()
            else:
                await c.disconnect()
        except Exception:
            pass
    if not keep_files:
        delete_account()
