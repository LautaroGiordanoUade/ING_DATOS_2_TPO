from typing import Any
from uuid import UUID

from neo4j import AsyncDriver

from app.application.services.follow_job import FollowJob
from app.core.exceptions import ConflictError, FeatureNotImplementedError


class Neo4jSocialGraphRepository:
    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    async def follow(self, user_id: UUID, followed_user_id: UUID) -> None:
        from uuid import uuid4

        await self.set_follow_state(
            FollowJob(
                operation_id=uuid4(),
                follower_id=user_id,
                followed_id=followed_user_id,
                actor_id=user_id,
                action="follow",
                desired="accepted",
            )
        )

    async def unfollow(self, user_id: UUID, followed_user_id: UUID) -> None:
        from uuid import uuid4

        await self.set_follow_state(
            FollowJob(
                operation_id=uuid4(),
                follower_id=user_id,
                followed_id=followed_user_id,
                actor_id=user_id,
                action="unfollow",
                desired="none",
            )
        )

    async def follow_snapshot(self, follower_id: UUID, followed_id: UUID) -> dict[str, Any]:
        async with self._driver.session() as session:
            result = await session.run(
                """OPTIONAL MATCH (f:User {id:$f})-[r:FOLLOWS]->(a:User {id:$a})
                RETURN collect(properties(r)) AS relationships,
                EXISTS { MATCH (:User {id:$f})-[:BLOCKS]-(:User {id:$a}) } AS blocked""",
                f=str(follower_id),
                a=str(followed_id),
            )
            record = await result.single(strict=True)
            assert record is not None
            rows = record["relationships"]
            if len(rows) > 1:
                raise ConflictError("Relaciones legacy duplicadas; requiere reconciliacion")
            return {"relationship": dict(rows[0]) if rows else None, "blocked": record["blocked"]}

    async def set_follow_state(self, job: FollowJob) -> None:
        async with self._driver.session() as session:
            if job.desired == "none":
                result = await session.run(
                    "MATCH (:User {id:$f})-[r:FOLLOWS]->(:User {id:$a}) DELETE r",
                    f=str(job.follower_id),
                    a=str(job.followed_id),
                )
            else:
                result = await session.run(
                    """MERGE (f:User {id:$f}) ON CREATE SET f.account_status='active'
                    MERGE (a:User {id:$a}) ON CREATE SET a.account_status='active'
                    MERGE (f)-[r:FOLLOWS]->(a)
                    SET r.status=$status, r.operation_id=$op,
                        r.created_at=coalesce(r.created_at,$created)""",
                    f=str(job.follower_id),
                    a=str(job.followed_id),
                    status=job.desired,
                    op=str(job.operation_id),
                    created=job.created_at.isoformat(),
                )
            await result.consume()

    async def restore_follow(self, job: FollowJob) -> None:
        assert job.graph_snapshot is not None
        previous = job.graph_snapshot["relationship"]
        async with self._driver.session() as session:
            if previous is None:
                query = "MATCH (:User {id:$f})-[r:FOLLOWS]->(:User {id:$a}) DELETE r"
            else:
                query = (
                    "MATCH (f:User {id:$f}),(a:User {id:$a}) "
                    "MERGE (f)-[r:FOLLOWS]->(a) SET r=$props"
                )
            result = await session.run(
                query,
                f=str(job.follower_id),
                a=str(job.followed_id),
                props=previous or {},
            )
            await result.consume()

    async def follow_counts(self, user_id: UUID) -> dict[str, int]:
        async with self._driver.session() as session:
            result = await session.run(
                """OPTIONAL MATCH (f:User)-[r:FOLLOWS]->(u:User {id:$id})
                WHERE coalesce(r.status,'accepted')='accepted'
                WITH count(DISTINCT f) AS followers
                OPTIONAL MATCH (:User {id:$id})-[s:FOLLOWS]->(a:User)
                WHERE coalesce(s.status,'accepted')='accepted'
                RETURN followers, count(DISTINCT a) AS following""",
                id=str(user_id),
            )
            record = await result.single(strict=True)
            assert record is not None
            return {"followers": int(record["followers"]), "following": int(record["following"])}

    async def incoming_requests(self, user_id: UUID) -> tuple[UUID, ...]:
        async with self._driver.session() as session:
            result = await session.run(
                """MATCH (f:User)-[:FOLLOWS {status:'pending'}]->(:User {id:$id})
                WHERE coalesce(f.account_status,'active')='active'
                RETURN DISTINCT f.id AS id ORDER BY id""",
                id=str(user_id),
            )
            return tuple([UUID(row["id"]) async for row in result])

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
