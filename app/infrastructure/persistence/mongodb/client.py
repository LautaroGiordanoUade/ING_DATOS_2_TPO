from pymongo import AsyncMongoClient


def create_mongo_client(url: str) -> AsyncMongoClient[dict[str, object]]:
    return AsyncMongoClient(url)

