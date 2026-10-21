"""One-shot Compose prerequisite: repair known dev fixtures, then verify indexes."""

import asyncio
import json
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.indexes import ensure_mongo_indexes
from app.infrastructure.persistence.mongodb.p1_fixtures import migrate_p1_fixtures


async def initialize_database(
    database: AsyncDatabase[dict[str, Any]], *, development: bool
) -> dict[str, Any]:
    migration = await migrate_p1_fixtures(database, apply=True) if development else None
    # An error must propagate: Compose must not start dependents with missing indexes.
    await ensure_mongo_indexes(database)
    return {"fixture_migration": migration, "indexes_verified": True}


async def main() -> None:
    settings = get_settings()
    client = create_mongo_client(settings.mongodb_url)
    try:
        result = await initialize_database(
            client[settings.mongodb_database], development=settings.app_env == "development"
        )
        print(json.dumps(result), flush=True)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
