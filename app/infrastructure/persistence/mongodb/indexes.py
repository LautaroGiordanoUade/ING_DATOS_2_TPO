from pymongo.asynchronous.database import AsyncDatabase

from app.infrastructure.persistence.mongodb.repositories import MongoReactionRepository


async def ensure_mongo_indexes(database: AsyncDatabase[dict[str, object]]) -> None:
    """Crea los índices de MongoDB. Es seguro ejecutarlo en cada arranque."""
    await MongoReactionRepository(database).ensure_indexes()
    # Los demás problemas pueden agregar acá los índices de sus colecciones.