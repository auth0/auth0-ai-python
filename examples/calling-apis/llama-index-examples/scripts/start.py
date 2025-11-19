import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
from src.app.app import app

def main():
    config = Config()
    config.bind = ["0.0.0.0:3000"]
    config.worker_class = "asyncio"
    config.use_reloader = True

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(serve(app, config))
