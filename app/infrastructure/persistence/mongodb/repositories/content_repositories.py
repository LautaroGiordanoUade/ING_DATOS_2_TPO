from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import Comment, Post, Reaction
from app.infrastructure.persistence.mongodb.collections import MongoCollection
from app.infrastructure.persistence.mongodb.mappers.post_mapper import (
    document_to_post,
    post_to_document,
)

class MongoPostRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database
        self._collection = database[MongoCollection.POSTS.value]

    async def create(self, post: Post) -> Post:
        try:
            await self._collection.insert_one(post_to_document(post))
        except DuplicateKeyError:
            pass  # mismo id = misma publicación: un reintento no duplica nada
        return post

    async def get(self, post_id: UUID) -> Post | None:
        document = await self._collection.find_one({"_id": str(post_id)})
        return None if document is None else document_to_post(document)
    
    async def get_many(self, post_ids: tuple[UUID, ...]) -> tuple[Post, ...]:
        # TODO(TP): Implementar lectura por lote preservando el orden del feed.
        raise FeatureNotImplementedError("MongoPostRepository.get_many")

    async def list_recent_by_user(self, user_id: UUID, limit: int) -> tuple[Post, ...]:
        # TODO(TP): Implementar consulta de publicaciones recientes para trazabilidad.
        raise FeatureNotImplementedError("MongoPostRepository.list_recent_by_user")

    async def update_moderation_status(self, post_id: UUID, status: str) -> None:
        # TODO(TP): Actualizar el estado documental con control de concurrencia.
        raise FeatureNotImplementedError("MongoPostRepository.update_moderation_status")

    async def delete(self, post_id: UUID) -> None:
        # TODO(TP): Implementar compensación de creación de publicación.
        raise FeatureNotImplementedError("MongoPostRepository.delete")


class MongoCommentRepository:
    """Comentarios separados para evitar crecimiento ilimitado del documento Post."""

    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database

    async def create(self, comment: Comment) -> Comment:
        # TODO(TP): Persistir comentario y definir índices/consistencia.
        raise FeatureNotImplementedError("MongoCommentRepository.create")

    async def delete(self, comment_id: UUID) -> None:
        # TODO(TP): Implementar compensación de comentario.
        raise FeatureNotImplementedError("MongoCommentRepository.delete")


class MongoReactionRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database

    async def upsert(self, reaction: Reaction) -> Reaction:
        # TODO(TP): Garantizar una reacción por (post_id, user_id) con operación atómica.
        raise FeatureNotImplementedError("MongoReactionRepository.upsert")

    async def delete_for_user(self, post_id: UUID, user_id: UUID) -> None:
        # TODO(TP): Eliminar reacción y coordinar contador derivado.
        raise FeatureNotImplementedError("MongoReactionRepository.delete_for_user")

