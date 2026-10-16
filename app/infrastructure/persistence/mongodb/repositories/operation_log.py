from uuid import UUID

from pydantic import TypeAdapter
from pymongo.asynchronous.database import AsyncDatabase

from app.application.services.operation import OperationContext

_operation_adapter = TypeAdapter(OperationContext)


class MongoOperationLogRepository:
    """Durable operation snapshots; recovery orchestration remains separate."""

    def __init__(self, database: AsyncDatabase[dict[str, object]]) -> None:
        self._collection = database["operations"]

    async def save(self, operation: OperationContext) -> None:
        document = _operation_adapter.dump_python(operation, mode="json")
        document["_id"] = str(operation.operation_id)
        await self._collection.replace_one({"_id": document["_id"]}, document, upsert=True)

    async def get(self, operation_id: UUID) -> OperationContext | None:
        document = await self._collection.find_one({"_id": str(operation_id)})
        if document is None:
            return None
        document.pop("_id", None)
        return _operation_adapter.validate_python(document)
