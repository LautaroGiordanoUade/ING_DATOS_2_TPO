from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError
from pymongo import ASCENDING, ReturnDocument

from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import Comment, Post, Reaction
from app.infrastructure.persistence.mongodb.collections import MongoCollection
from app.infrastructure.persistence.mongodb.mappers.post_mapper import (
    document_to_post,
    post_to_document,
)
from app.infrastructure.persistence.mongodb.mappers.reaction_mapper import document_to_reaction

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
        self._collection = database[MongoCollection.REACTIONS.value]

    async def ensure_indexes(self) -> None:
        # Una sola reacción por persona y publicación: lo garantiza Mongo, no el código.
        await self._collection.create_index(
            [("post_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True,
            name="uq_reaction_post_user",
        )

    async def upsert(self, reaction: Reaction) -> Reaction | None:
        filtro = {"post_id": str(reaction.post_id), "user_id": str(reaction.user_id)}
        cambios = {
            "$set": {"kind": reaction.kind},
            "$setOnInsert": {"_id": str(reaction.id), "created_at": reaction.created_at},
        }
        try:
            anterior = await self._collection.find_one_and_update(
                filtro, cambios, upsert=True, return_document=ReturnDocument.BEFORE
            )
        except DuplicateKeyError:
            # Dos pedidos simultáneos intentaron crear la primera reacción.
            # El segundo reintenta y ahora la encuentra: se convierte en cambio.
            anterior = await self._collection.find_one_and_update(
                filtro, cambios, upsert=True, return_document=ReturnDocument.BEFORE
            )
        return None if anterior is None else document_to_reaction(anterior)

    async def delete_for_user(self, post_id: UUID, user_id: UUID) -> Reaction | None:
        borrada = await self._collection.find_one_and_delete(
            {"post_id": str(post_id), "user_id": str(user_id)}
        )
        return None if borrada is None else document_to_reaction(borrada)