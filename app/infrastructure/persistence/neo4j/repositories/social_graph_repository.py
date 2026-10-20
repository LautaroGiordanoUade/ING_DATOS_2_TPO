from uuid import UUID

from neo4j import AsyncDriver

from app.core.exceptions import FeatureNotImplementedError


class Neo4jSocialGraphRepository:
    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    async def follow(self, user_id: UUID, followed_user_id: UUID) -> None:
        # TODO(TP): Implementar Cypher idempotente para follow/pending follow.
        raise FeatureNotImplementedError("Neo4jSocialGraphRepository.follow")

    async def unfollow(self, user_id: UUID, followed_user_id: UUID) -> None:
        # TODO(TP): Implementar consulta Cypher de unfollow.
        raise FeatureNotImplementedError("Neo4jSocialGraphRepository.unfollow")

    async def follower_ids(self, user_id: UUID) -> tuple[UUID, ...]:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (follower:User)-[r:FOLLOWS]->(author:User {id: $user_id})
                WHERE coalesce(r.status, 'accepted') = 'accepted'
                  AND coalesce(follower.account_status, 'active') = 'active'
                  AND NOT (follower)-[:BLOCKS]-(author)
                RETURN DISTINCT follower.id AS id ORDER BY id
                """,
                user_id=str(user_id),
            )
            return tuple([UUID(record["id"]) async for record in result])

    async def get_mutual_friends(self, user_id: UUID, other_user_id: UUID) -> tuple[UUID, ...]:
        # TODO(TP): Implementar consulta Cypher para amigos en común.
        raise FeatureNotImplementedError("Neo4jSocialGraphRepository.get_mutual_friends")

    async def get_suggested_accounts(self, user_id: UUID, limit: int) -> tuple[UUID, ...]:
        # TODO(TP): Implementar Cypher de recomendaciones con exclusiones e intereses.
        raise FeatureNotImplementedError("Neo4jSocialGraphRepository.get_suggested_accounts")

    async def trace_relationships(self, user_id: UUID) -> dict[str, object]:
        # TODO(TP): Implementar consulta de relaciones para trazabilidad multi-motor.
        raise FeatureNotImplementedError("Neo4jSocialGraphRepository.trace_relationships")
