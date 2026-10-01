"""Файловое хранилище: настройки, аккаунт, список найденных групп."""

DEFAULT_SETTINGS = {
    "min_members": 1000,
    "min_msgs": 20,            # N сообщений...
    "window_hours": 24,        # ...за X часов
    "min_unique_senders": 5,   # уникальных авторов среди последних 100 сообщений
    "min_age_days": 30,
    "max_age_days": 1825,      # ~5 лет; старше + малоактивная = отсев
    "min_desc_len": 20,
    "language": "ru",          # ru | uk | en | any
    "stop_words": [],
    "delay": 1.5,              # пауза между проверками групп, сек
}

# ключ: (название, тип)
SETTINGS_META = {
    "min_members": ("Мин. подписчиков", "int"),
    "min_msgs": ("Мин. сообщений за период (N)", "int"),
    "window_hours": ("Период активности, часов (X)", "int"),
    "min_unique_senders": ("Мин. уникальных авторов", "int"),
    "min_age_days": ("Мин. возраст группы, дней", "int"),
    "max_age_days": ("Макс. возраст для малоактивных, дней", "int"),
    "min_desc_len": ("Мин. длина описания, символов", "int"),
    "language": ("Язык группы", "lang"),
    "stop_words": ("Стоп-слова", "list"),
    "delay": ("Пауза между проверками, сек", "float"),
}


def data_dir():
    import os
    d = os.getenv("DATA_DIR", "data")
    os.makedirs(d, exist_ok=True)
    return d


def path(name):
    import os
    return os.path.join(data_dir(), name)


def load_json(name, default):
    import json
    import os
    p = path(name)
    if not os.path.exists(p):
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(name, data):
    import json
    import os
    p = path(name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


# ---------- настройки ----------
def get_settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(load_json("settings.json", {}).get("filters", {}))
    return s


def update_setting(key, value):
    raw = load_json("settings.json", {})
    raw.setdefault("filters", {})[key] = value
    save_json("settings.json", raw)


# ---------- владелец бота ----------
def get_owner():
    import os
    env = os.getenv("OWNER_ID", "").strip()
    if env.isdigit():
        return int(env)
    return load_json("settings.json", {}).get("owner_id")


def set_owner(user_id):
    raw = load_json("settings.json", {})
    raw["owner_id"] = user_id
    save_json("settings.json", raw)


# ---------- аккаунт ----------
def load_account():
    return load_json("account.json", None)


def save_account(api_id, api_hash):
    save_json("account.json", {"api_id": api_id, "api_hash": api_hash})


def delete_account():
    import glob
    import os
    for f in glob.glob(path("user.session*")) + [path("account.json")]:
        try:
            os.remove(f)
        except OSError:
            pass


# ---------- найденные группы ----------
def load_found_ids():
    return set(load_json("found_groups.json", []))


def save_found_ids(ids):
    save_json("found_groups.json", sorted(ids))
