from neo4j import AsyncDriver, AsyncGraphDatabase


def create_neo4j_driver(uri: str, user: str, password: str) -> AsyncDriver:
    return AsyncGraphDatabase.driver(uri, auth=(user, password))

