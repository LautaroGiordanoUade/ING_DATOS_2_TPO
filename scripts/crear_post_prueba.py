import asyncio
from uuid import UUID

from pymongo import AsyncMongoClient

from app.core.config import get_settings
from app.domain.entities import Post
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.database import get_mongo_database
from app.infrastructure.persistence.mongodb.repositories import MongoPostRepository

AUTOR = UUID("00000000-0000-0000-0000-000000000001")
POST = UUID("10000000-0000-0000-0000-000000000001")


async def main() -> None:
    settings = get_settings()
    client = AsyncMongoClient(settings.mongodb_url)
    db = get_mongo_database(client, settings.mongodb_database)
    await MongoPostRepository(db).create(
        Post(
            id=POST,
            user_id=AUTOR,
            text="Publicación de prueba",
            moderation_status=ModerationStatus.APPROVED,
        )
    )
    print("Post de prueba listo:", POST, "| autor:", AUTOR)
    await client.close()


asyncio.run(main())