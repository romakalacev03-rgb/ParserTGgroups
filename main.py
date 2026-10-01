"""Точка входа: python main.py"""


def load_env(file=".env"):
    import os
    if not os.path.exists(file):
        return
    with open(file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


async def start_health_server(port):
    """Мини-HTTP сервер для хостингов, которые требуют открытый порт (Render и т.п.)."""
    from aiohttp import web

    async def ok(request):
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/health", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()


async def main():
    import logging
    import os
    from aiogram import Bot, Dispatcher
    from handlers import build_router

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Не задана переменная окружения BOT_TOKEN")

    port = os.getenv("PORT")
    if port and port.isdigit():
        await start_health_server(int(port))

    bot = Bot(token)
    dp = Dispatcher()
    dp.include_router(build_router())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    load_env()
    asyncio.run(main())
