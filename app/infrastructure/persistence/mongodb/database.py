from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase


def get_mongo_database(
    client: AsyncMongoClient[dict[str, object]], database_name: str
) -> AsyncDatabase[dict[str, object]]:
    return client[database_name]

