from pymongo.asynchronous.database import AsyncDatabase

from app.infrastructure.persistence.mongodb.repositories import (
    MongoCommentRepository,
    MongoReactionRepository,
)


async def ensure_mongo_indexes(database: AsyncDatabase[dict[str, object]]) -> None:
    """Crea los índices de MongoDB. Es seguro ejecutarlo en cada arranque."""
    await MongoReactionRepository(database).ensure_indexes()
    await MongoCommentRepository(database).ensure_indexes()
    
#Los dos métodos son idempotentes: delete_one sobre algo que no existe no falla, y create ignora el duplicado. 
# Eso permite reintentar una compensación sin riesgo.