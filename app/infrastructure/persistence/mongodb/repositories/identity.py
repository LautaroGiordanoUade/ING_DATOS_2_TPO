from dataclasses import asdict, fields
from typing import Any
from uuid import UUID

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AuthenticationError, ConflictError
from app.domain.entities import User
from app.domain.entities.models import AccountStatus, AccountType
from app.domain.interests import normalize_interests
from app.domain.recommendations import InterestProfile
from app.infrastructure.persistence.mongodb.repositories.moderation import (
    MongoModerationRepository as MongoModerationRepository,
)


class MongoUserRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._collection = database["users"]

    async def ensure_indexes(self) -> None:
        for field in ("username", "email"):
            await self._collection.create_index(field, unique=True)
        await self._collection.create_index(
            [("interests", 1), ("account_status", 1), ("_id", 1)],
            name="ix_user_interests_status_id",
        )

    @staticmethod
    def _user(document: dict[str, Any]) -> User:
        data = dict(document)
        data["id"] = UUID(data.pop("_id"))
        data["account_type"] = AccountType(data.get("account_type", "public"))
        data["account_status"] = AccountStatus(data.get("account_status", "active"))
        data["interests"] = tuple(data.get("interests") or ())
        return User(
            **{key: value for key, value in data.items() if key in {f.name for f in fields(User)}}
        )

    async def get(self, user_id: UUID) -> User | None:
        doc = await self._collection.find_one({"_id": str(user_id)})
        return None if doc is None else self._user(doc)

    async def by_username(self, username: str) -> User | None:
        doc = await self._collection.find_one({"username": username})
        return None if doc is None else self._user(doc)

    async def create(self, user: User) -> User:
        await self.ensure_indexes()
        doc = asdict(user)
        doc["_id"] = str(doc.pop("id"))
        try:
            await self._collection.insert_one(doc)
        except DuplicateKeyError as exc:
            raise ConflictError("Username or email already exists") from exc
        return user

    async def update_account_status(self, user_id: UUID, status: str) -> None:
        await self._collection.update_one(
            {"_id": str(user_id)}, {"$set": {"account_status": AccountStatus(status).value}}
        )

    async def update_interests(self, user_id: UUID, interests: tuple[str, ...]) -> User:
        interests = normalize_interests(list(interests))
        doc = await self._collection.find_one_and_update(
            {"_id": str(user_id), "account_status": {"$ne": "suspended"}},
            {"$set": {"interests": list(interests)}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            raise AuthenticationError("Account unavailable")
        return self._user(doc)

    async def interest_profiles(self, ids: tuple[UUID, ...]) -> tuple[InterestProfile, ...]:
        if not ids:
            return ()
        docs = await self._collection.find(
            {"_id": {"$in": [str(i) for i in ids]}, "account_status": {"$ne": "suspended"}},
            {"interests": 1},
        ).to_list()
        return tuple(self._interest_profile(doc) for doc in docs)

    @staticmethod
    def _interest_profile(doc: dict[str, Any]) -> InterestProfile:
        return InterestProfile(UUID(doc["_id"]), tuple(doc.get("interests") or ()))

    async def interest_candidates(
        self, interests: tuple[str, ...], after: UUID | None, limit: int
    ) -> tuple[InterestProfile, ...]:
        if not interests:
            return ()
        query: dict[str, object] = {
            "interests": {"$in": list(interests)},
            "account_status": {"$ne": "suspended"},
        }
        if after is not None:
            query["_id"] = {"$gt": str(after)}
        docs = await (
            self._collection.find(query, {"interests": 1}).sort("_id", 1).limit(limit).to_list()
        )
        return tuple(self._interest_profile(doc) for doc in docs)

    async def active_ids(self, user_ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if not user_ids:
            return ()
        docs = await self._collection.find(
            {"_id": {"$in": [str(i) for i in user_ids]}, "account_status": {"$ne": "suspended"}},
            {"_id": 1},
        ).to_list()
        active = {str(doc["_id"]) for doc in docs}
        return tuple(identifier for identifier in user_ids if str(identifier) in active)

    async def is_suspended(self, user_id: UUID) -> bool:
        return (
            await self._collection.find_one(
                {"_id": str(user_id), "account_status": "suspended"}, {"_id": 1}
            )
            is not None
        )
