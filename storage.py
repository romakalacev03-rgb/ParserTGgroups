"""Файловое хранилище: настройки, аккаунт, список найденных групп."""

DEFAULT_SETTINGS = {
    "use_filters": True,       # Использовать ли строгие фильтры
    "min_members": 100,        # Снижено до 100
    "min_msgs": 5,             # Снижено до 5
    "window_hours": 24,        
    "min_unique_senders": 2,   # Снижено
    "min_age_days": 0,         # Разрешить новые группы
    "max_age_days": 3650,      
    "min_desc_len": 0,         # 0 = разрешить группы без описания
    "language": "any",         # По умолчанию любой язык
    "stop_words": [],
    "delay": 1.5,              
}

SETTINGS_META = {
    "use_filters": ("Использовать строгие фильтры (да/нет)", "bool"),
    "min_members": ("Мин. подписчиков", "int"),
    "min_msgs": ("Мин. сообщений за период (N)", "int"),
    "window_hours": ("Период активности, часов (X)", "int"),
    "min_unique_senders": ("Мин. уникальных авторов", "int"),
    "min_age_days": ("Мин. возраст группы, дней", "int"),
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

def get_settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(load_json("settings.json", {}).get("filters", {}))
    return s

def update_setting(key, value):
    raw = load_json("settings.json", {})
    raw.setdefault("filters", {})[key] = value
    save_json("settings.json", raw)

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

def load_found_ids():
    return set(load_json("found_groups.json", []))

def save_found_ids(ids):
    save_json("found_groups.json", sorted(ids))
