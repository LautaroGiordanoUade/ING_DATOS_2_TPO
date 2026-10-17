import asyncio
from uuid import uuid4

from pymongo import AsyncMongoClient

from app.core.config import get_settings
from app.domain.entities import Post, Reaction
from app.infrastructure.persistence.mongodb.database import get_mongo_database
from app.infrastructure.persistence.mongodb.repositories import (
    MongoPostRepository,
    MongoReactionRepository,
)


async def main() -> None:
    settings = get_settings()
    client = AsyncMongoClient(settings.mongodb_url)
    db = get_mongo_database(client, settings.mongodb_database)
    posts = MongoPostRepository(db)
    reactions = MongoReactionRepository(db)
    await reactions.ensure_indexes()

    autor, lector = uuid4(), uuid4()
    post = await posts.create(Post(user_id=autor, text="prueba"))
    leido = await posts.get(post.id)
    print("get devuelve el post:", leido is not None and leido.id == post.id)

    r1 = await reactions.upsert(Reaction(post_id=post.id, user_id=lector, kind="like"))
    print("1ra reacción -> anterior (esperado None):", r1)
    r2 = await reactions.upsert(Reaction(post_id=post.id, user_id=lector, kind="love"))
    print("cambio -> anterior (esperado like):", r2.kind if r2 else None)
    r3 = await reactions.delete_for_user(post.id, lector)
    print("borrar -> borrada (esperado love):", r3.kind if r3 else None)
    r4 = await reactions.delete_for_user(post.id, lector)
    print("borrar otra vez -> (esperado None):", r4)

    await db["posts"].delete_one({"_id": str(post.id)})
    await client.close()


asyncio.run(main())