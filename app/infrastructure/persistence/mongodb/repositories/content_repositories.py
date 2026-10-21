from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import FeatureNotImplementedError
from app.domain.entities import Comment, Post, Reaction
from app.infrastructure.persistence.mongodb.collections import MongoCollection
from app.infrastructure.persistence.mongodb.mappers.comment_mapper import comment_to_document
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
        document = await self._collection.find_one(
            {
                "_id": str(post_id),
                "publication_state": {"$ne": "pending"},
                "moderation_status": {"$ne": "hidden"},
            }
        )
        if document is None:
            return None
        author = await self._database["users"].find_one(
            {"_id": document["user_id"], "account_status": "suspended"}
        )
        return None if author else document_to_post(document)

    async def get_many(self, post_ids: tuple[UUID, ...]) -> tuple[Post, ...]:
        docs = await self._collection.find(
            {
                "_id": {"$in": [str(i) for i in post_ids]},
                "publication_state": {"$ne": "pending"},
                "moderation_status": {"$ne": "hidden"},
                "visibility": "public",
            }
        ).to_list()
        blocked = {
            str(row["_id"])
            async for row in self._database["users"].find(
                {
                    "_id": {"$in": list({str(doc["user_id"]) for doc in docs})},
                    "account_status": "suspended",
                },
                {"_id": 1},
            )
        }
        by_id = {
            str(doc["_id"]): document_to_post(doc)
            for doc in docs
            if str(doc["user_id"]) not in blocked
        }
        return tuple(by_id[str(i)] for i in post_ids if str(i) in by_id)

    async def list_recent_by_user(self, user_id: UUID, limit: int) -> tuple[Post, ...]:
        if await self._database["users"].find_one(
            {"_id": str(user_id), "account_status": "suspended"}
        ):
            return ()
        docs = (
            await self._collection.find(
                {
                    "user_id": str(user_id),
                    "publication_state": {"$ne": "pending"},
                    "moderation_status": {"$ne": "hidden"},
                    "visibility": "public",
                }
            )
            .sort("published_at", -1)
            .limit(limit)
            .to_list()
        )
        return tuple(document_to_post(doc) for doc in docs)

    async def update_moderation_status(self, post_id: UUID, status: str) -> None:
        await self._collection.update_one(
            {"_id": str(post_id)}, {"$set": {"moderation_status": status}}
        )

    async def delete(self, post_id: UUID) -> None:
        # TODO(TP): Implementar compensación de creación de publicación.
        raise FeatureNotImplementedError("MongoPostRepository.delete")


class MongoCommentRepository:
    """Comentarios separados para evitar crecimiento ilimitado del documento Post."""

    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._database = database
        self._collection = database[MongoCollection.COMMENTS.value]

    async def ensure_indexes(self) -> None:
        # Para listar los comentarios de una publicación, del más nuevo al más viejo.
        await self._collection.create_index(
            [("post_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_comment_post_created",
        )

    async def create(self, comment: Comment) -> Comment:
        try:
            await self._collection.insert_one(comment_to_document(comment))
        except DuplicateKeyError:
            pass  # mismo id = mismo comentario: un reintento no duplica nada
        return comment

    async def delete(self, comment_id: UUID) -> None:
        await self._collection.delete_one({"_id": str(comment_id)})


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
