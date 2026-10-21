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
                  AND coalesce(author.account_status, 'active') = 'active'
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
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {id:$id})-[:FOLLOWS {status:'accepted'}]->(middle:User)
                      -[:FOLLOWS {status:'accepted'}]->(candidate:User)
                WHERE candidate <> u AND coalesce(u.account_status,'active')='active'
                  AND coalesce(middle.account_status,'active')='active'
                  AND coalesce(candidate.account_status,'active')='active'
                  AND NOT (u)-[:FOLLOWS]->(candidate) AND NOT (u)-[:BLOCKS]-(candidate)
                RETURN candidate.id AS id, count(*) AS score ORDER BY score DESC, id LIMIT $limit
            """,
                id=str(user_id),
                limit=limit,
            )
            return tuple([UUID(record["id"]) async for record in result])

    async def trace_relationships(self, user_id: UUID) -> dict[str, object]:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {id:$id})-[r]-(other:User)
                RETURN type(r) AS kind, startNode(r)=u AS outgoing,
                       other.id AS other_id, coalesce(r.status,'accepted') AS status
                ORDER BY kind, other_id
            """,
                id=str(user_id),
            )
            rows = [dict(record) async for record in result]
        return {
            "followers": [
                row["other_id"] for row in rows if row["kind"] == "FOLLOWS" and not row["outgoing"]
            ],
            "following": [
                row["other_id"] for row in rows if row["kind"] == "FOLLOWS" and row["outgoing"]
            ],
            "blocked": [row["other_id"] for row in rows if row["kind"] == "BLOCKS"],
            "edges": rows,
        }

    async def account_snapshot(self, user_id: UUID) -> dict[str, object]:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (u:User {id:$id}) RETURN u.account_status AS status", id=str(user_id)
            )
            row = await result.single()
            return {"exists": row is not None, "account_status": row["status"] if row else None}

    async def set_account_status(self, user_id: UUID, status: str) -> None:
        async with self._driver.session() as session:
            result = await session.run(
                "MERGE (u:User {id:$id}) SET u.account_status=$status",
                id=str(user_id),
                status=status,
            )
            await result.consume()

    async def restore_account(self, user_id: UUID, snapshot: dict[str, object]) -> None:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {id:$id}) SET u.account_status=$status
                WITH u WHERE $created AND NOT (u)--() DELETE u
            """,
                id=str(user_id),
                status=snapshot.get("account_status"),
                created=not snapshot["exists"],
            )
            await result.consume()
