"""Complete legacy P1 users without deleting data. Dry-run unless --apply is given."""

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.indexes import ensure_mongo_indexes
from app.infrastructure.persistence.mongodb.p1_fixtures import migrate_p1_fixtures


async def main(apply: bool) -> None:
    settings = get_settings()
    if settings.app_env != "development":
        raise RuntimeError("P1 fixture migration requires APP_ENV=development")
    client = create_mongo_client(settings.mongodb_url)
    try:
        database = client[settings.mongodb_database]
        result = await migrate_p1_fixtures(database, apply=apply)
        if apply:
            await ensure_mongo_indexes(database)
        print(json.dumps({**result, "indexes_verified": apply}))
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
