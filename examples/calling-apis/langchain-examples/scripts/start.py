import asyncio

from hypercorn.asyncio import serve
from hypercorn.config import Config
from src.app.app import app


def main():
    config = Config()
    config.bind = ["localhost:3000"]
    config.worker_class = "asyncio"
    config.use_reloader = True

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(serve(app, config))
