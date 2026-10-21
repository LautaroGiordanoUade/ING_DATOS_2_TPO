"""Prepare the database before the API accepts requests."""

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.infrastructure.persistence.mongodb.indexes import ensure_mongo_indexes
from app.infrastructure.persistence.mongodb.p1_fixtures import migrate_p1_fixtures


async def initialize_database(
    database: AsyncDatabase[dict[str, Any]], *, development: bool
) -> dict[str, Any]:
    migration = await migrate_p1_fixtures(database, apply=True) if development else None
    # Fail startup rather than serving with missing required indexes.
    await ensure_mongo_indexes(database)
    return {"fixture_migration": migration, "indexes_verified": True}
