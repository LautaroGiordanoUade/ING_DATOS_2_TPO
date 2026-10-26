"""P4 against real MongoDB and Neo4j; isolated database and UUID nodes per test."""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.core.config import get_settings
from app.domain.entities import User
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires all three real engines"
)


@dataclass
class RecommendationsHarness:
    h: Harness
    users: MongoUserRepository
    graph: Neo4jSocialGraphRepository
    created_ids: list[str]

    async def create_user(self, label: str, status: str = "active") -> User:
        actor = User(
            id=uuid4(),
            username=f"p4_{label}_{uuid4().hex[:6]}",
            full_name=f"P4 {label}",
            email=f"{label}_{uuid4().hex[:6]}@p4.test",
            password_hash=self.h.user.password_hash,
            account_status=status,  # type: ignore[arg-type]
        )
        await self.users.create(actor)
        self.created_ids.append(str(actor.id))
        async with self.h.resources.neo4j.session() as session:
            res = await session.run(
                "MERGE (u:User {id:$id}) SET u.account_status=$status",
                id=str(actor.id),
                status=status,
            )
            await res.consume()
        return actor

    async def add_follow(self, follower: User, followed: User, status: str = "accepted") -> None:
        async with self.h.resources.neo4j.session() as session:
            res = await session.run(
                """
                MERGE (f:User {id:$f})
                MERGE (a:User {id:$a})
                MERGE (f)-[r:FOLLOWS]->(a)
                SET r.status=$status
                """,
                f=str(follower.id),
                a=str(followed.id),
                status=status,
            )
            await res.consume()

    async def add_block(self, blocker: User, blocked: User) -> None:
        async with self.h.resources.neo4j.session() as session:
            res = await session.run(
                """
                MERGE (b:User {id:$b})
                MERGE (t:User {id:$t})
                MERGE (b)-[:BLOCKS]->(t)
                """,
                b=str(blocker.id),
                t=str(blocked.id),
            )
            await res.consume()


@pytest.fixture
async def p4(harness: Harness) -> AsyncIterator[RecommendationsHarness]:
    database = harness.resources.mongo_client[get_settings().mongodb_database]
    users = MongoUserRepository(database)
    graph = Neo4jSocialGraphRepository(harness.resources.neo4j)
    created: list[str] = []
    try:
        yield RecommendationsHarness(harness, users, graph, created)
    finally:
        if created:
            async with harness.resources.neo4j.session() as session:
                res = await session.run(
                    "MATCH (u:User) WHERE u.id IN $ids DETACH DELETE u",
                    ids=created,
                )
                await res.consume()


async def test_mutual_friends_orders_deterministically_and_excludes_pending_and_blocks(
    p4: RecommendationsHarness,
) -> None:
    u1 = await p4.create_user("u1")
    u2 = await p4.create_user("u2")
    common_a = await p4.create_user("common_a")
    common_b = await p4.create_user("common_b")
    pending_friend = await p4.create_user("pending")
    blocked_friend = await p4.create_user("blocked")

    for friend in (common_a, common_b, blocked_friend):
        await p4.add_follow(u1, friend, "accepted")
        await p4.add_follow(u2, friend, "accepted")

    await p4.add_follow(u1, pending_friend, "accepted")
    await p4.add_follow(u2, pending_friend, "pending")
    await p4.add_block(u1, blocked_friend)

    response = await p4.h.client.get(
        f"/api/v1/problems/4/mutual-friends?user_id={u1.id}&other_user_id={u2.id}"
    )
    assert response.status_code == 200
    expected = sorted([str(common_a.id), str(common_b.id)])
    assert response.json() == expected


async def test_mutual_friends_blocks_between_queried_users_returns_empty(
    p4: RecommendationsHarness,
) -> None:
    u1 = await p4.create_user("u1")
    u2 = await p4.create_user("u2")
    common = await p4.create_user("common")
    await p4.add_follow(u1, common, "accepted")
    await p4.add_follow(u2, common, "accepted")
    await p4.add_block(u2, u1)

    response = await p4.h.client.get(
        f"/api/v1/problems/4/mutual-friends?user_id={u1.id}&other_user_id={u2.id}"
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_recommendations_ranks_by_score_and_excludes_followed_blocked_and_pending(
    p4: RecommendationsHarness,
) -> None:
    requester = await p4.create_user("requester")
    bridge_1 = await p4.create_user("bridge1")
    bridge_2 = await p4.create_user("bridge2")
    blocked_bridge = await p4.create_user("blocked_bridge")
    top_candidate = await p4.create_user("top")
    second_candidate = await p4.create_user("second")
    already_followed = await p4.create_user("followed")
    blocked_candidate = await p4.create_user("blocked_cand")
    only_via_blocked_bridge = await p4.create_user("via_blocked")

    await p4.add_follow(requester, bridge_1, "accepted")
    await p4.add_follow(requester, bridge_2, "accepted")
    await p4.add_follow(requester, blocked_bridge, "accepted")
    await p4.add_block(requester, blocked_bridge)

    # top_candidate is followed by both active bridges (score = 2)
    await p4.add_follow(bridge_1, top_candidate, "accepted")
    await p4.add_follow(bridge_2, top_candidate, "accepted")

    # second_candidate is followed by 1 active bridge (score = 1)
    await p4.add_follow(bridge_1, second_candidate, "accepted")

    # Excluded candidates
    await p4.add_follow(bridge_1, already_followed, "accepted")
    await p4.add_follow(requester, already_followed, "pending")
    await p4.add_follow(bridge_1, blocked_candidate, "accepted")
    await p4.add_block(blocked_candidate, requester)
    await p4.add_follow(blocked_bridge, only_via_blocked_bridge, "accepted")

    response = await p4.h.client.get(f"/api/v1/problems/4/recommendations/{requester.id}")
    assert response.status_code == 200
    assert response.json() == [str(top_candidate.id), str(second_candidate.id)]


async def test_recommendations_oversamples_when_mongo_marks_top_candidates_suspended(
    p4: RecommendationsHarness,
) -> None:
    requester = await p4.create_user("requester")
    bridge = await p4.create_user("bridge")
    await p4.add_follow(requester, bridge, "accepted")

    candidates = [await p4.create_user(f"cand_{idx}") for idx in range(12)]
    for cand in candidates:
        await p4.add_follow(bridge, cand, "accepted")

    ordered_by_id = sorted(candidates, key=lambda c: str(c.id))
    # Suspend the first 2 in MongoDB only (simulating in-flight suspension before Neo4j step)
    await p4.users.update_account_status(ordered_by_id[0].id, "suspended")
    await p4.users.update_account_status(ordered_by_id[1].id, "suspended")

    response = await p4.h.client.get(f"/api/v1/problems/4/recommendations/{requester.id}")
    assert response.status_code == 200
    data: list[str] = response.json()
    assert len(data) == 10
    assert data == [str(c.id) for c in ordered_by_id[2:12]]
    assert all(UUID(uid) not in (ordered_by_id[0].id, ordered_by_id[1].id) for uid in data)
