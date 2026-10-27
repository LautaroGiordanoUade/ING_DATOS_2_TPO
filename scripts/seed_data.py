"""Local compatibility entrypoint. Prefer python -m app.tools.seed_data inside Docker."""

import asyncio

from app.tools.seed_data import run

if __name__ == "__main__":
    asyncio.run(run())
