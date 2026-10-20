from dataclasses import asdict
from typing import Any
from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError
from app.domain.entities import User
from app.domain.entities.models import AccountStatus, AccountType
from app.infrastructure.persistence.mongodb.repositories.moderation import (
    MongoModerationRepository as MongoModerationRepository,
)


class MongoUserRepository:
    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._collection = database["users"]

    async def ensure_indexes(self) -> None:
        for field in ("username", "email"):
            await self._collection.create_index(field, unique=True)

    @staticmethod
    def _user(document: dict[str, Any]) -> User:
        data = dict(document)
        data["id"] = UUID(data.pop("_id"))
        data["account_type"] = AccountType(data.get("account_type", "public"))
        data["account_status"] = AccountStatus(data.get("account_status", "active"))
        return User(**data)

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
