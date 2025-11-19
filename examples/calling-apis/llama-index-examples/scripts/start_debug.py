import asyncio
from hypercorn.config import Config
from hypercorn.asyncio import serve
from src.app.app import app

async def run_server():
    config = Config()
    config.bind = ["0.0.0.0:3000"]
    config.worker_class = "asyncio"
    config.use_reloader = False  # Disable reloader for debugging

    print(f"Starting server on {config.bind}...")
    try:
        await serve(app, config)
    except Exception as e:
        print(f"Server error: {e}")
        raise

def main():
    asyncio.run(run_server())

if __name__ == "__main__":
    main()
