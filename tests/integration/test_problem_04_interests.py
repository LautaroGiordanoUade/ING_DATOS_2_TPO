import json
import os

import pytest

from app.application.use_cases import problem_04_social_recommendations as recommendations
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.domain.entities import User
from tests.integration.support import harness as harness
from tests.integration.test_problem_04_recommendations import RecommendationsHarness
from tests.integration.test_problem_04_recommendations import p4 as p4

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires all three real engines"
)


async def test_editing_interests_is_authenticated_atomic_and_legacy_safe(
    p4: RecommendationsHarness,
) -> None:
    h = p4.h
    collection = h.resources.mongo_client[get_settings().mongodb_database]["users"]
    await collection.update_one({"_id": str(h.user.id)}, {"$unset": {"interests": ""}})
    path = "/api/v1/users/me/interests"
    assert (await h.client.put(path, json={"interests": ["python"]})).status_code == 401
    before = (await h.client.get("/api/v1/users/me", headers=h.headers())).json()
    assert before["interests"] == []
    response = await h.client.put(
        path, headers=h.headers(), json={"interests": [" Python ", "PYTHON", "Música"]}
    )
    assert response.status_code == 200
    assert response.json()["interests"] == ["python", "música"]
    assert response.json()["id"] == before["id"]
    other = await p4.users.get(h.moderator.id)
    assert other is not None and other.interests == ()
    replay = await h.client.put(path, headers=h.headers(), json={"interests": ["python", "música"]})
    assert replay.json() == response.json()
    assert (
        await h.client.put(path, headers=h.headers(), json={"interests": [" "]})
    ).status_code == 422
    cleared = await h.client.put(path, headers=h.headers(), json={"interests": []})
    assert cleared.json()["interests"] == []
    await p4.users.update_account_status(h.user.id, "suspended")
    assert (
        await h.client.put(path, headers=h.headers(), json={"interests": ["python"]})
    ).status_code == 401
    with pytest.raises(AuthenticationError):
        await p4.users.update_interests(h.user.id, ("python",))
    await p4.users.ensure_indexes()
    plan = (
        await collection.find(
            {"interests": {"$in": ["python"]}, "account_status": {"$ne": "suspended"}}
        )
        .hint("ix_user_interests_status_id")
        .explain()
    )
    assert "ix_user_interests_status_id" in json.dumps(plan)


async def test_interests_rank_before_connections_and_editing_changes_order(
    p4: RecommendationsHarness,
) -> None:
    actor = await p4.create_user("actor")
    a, b = await p4.create_user("bridge_a"), await p4.create_user("bridge_b")
    popular = await p4.create_user("popular")
    relevant = await p4.create_user("relevant")
    await p4.add_follow(actor, a)
    await p4.add_follow(actor, b)
    await p4.add_follow(a, popular)
    await p4.add_follow(b, popular)
    await p4.add_follow(a, relevant)
    await p4.users.update_interests(relevant.id, ("python", "música"))
    path = f"/api/v1/problems/4/recommendations/{actor.id}"
    assert (await p4.h.client.get(path)).json() == [str(popular.id), str(relevant.id)]
    await p4.users.update_interests(actor.id, ("python",))
    assert (await p4.h.client.get(path)).json() == [str(relevant.id), str(popular.id)]
    await p4.users.update_interests(actor.id, ())
    assert (await p4.h.client.get(path)).json() == [str(popular.id), str(relevant.id)]


async def test_ranking_scans_past_thirty_and_multiple_batches(
    p4: RecommendationsHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recommendations, "_CANDIDATE_BATCH", 7)
    actor, bridge = await p4.create_user("actor"), await p4.create_user("bridge")
    await p4.add_follow(actor, bridge)
    candidates = [await p4.create_user(f"candidate{i}") for i in range(40)]
    for candidate in candidates:
        await p4.add_follow(bridge, candidate)
    ordered = sorted(candidates, key=lambda candidate: str(candidate.id))
    await p4.users.update_interests(actor.id, ("python",))
    await p4.users.update_interests(ordered[-1].id, ("python",))
    response = await p4.h.client.get(f"/api/v1/problems/4/recommendations/{actor.id}")
    assert response.status_code == 200
    assert response.json() == [str(ordered[-1].id)] + [str(c.id) for c in ordered[:9]]


async def test_interest_fallback_handles_missing_graph_nodes_and_exclusions(
    p4: RecommendationsHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recommendations, "_CANDIDATE_BATCH", 2)
    actor = p4.h.user  # Legacy registered user without a Neo4j node.
    p4.created_ids.append(str(actor.id))  # The block/follow helpers may later create its node.
    await p4.users.update_interests(actor.id, ("python", "música"))
    no_node = User(
        username="no_node",
        full_name="No node",
        email="no@node.test",
        password_hash="hash",
        interests=("python",),
    )
    await p4.users.create(no_node)
    path = f"/api/v1/problems/4/recommendations/{actor.id}"
    assert (await p4.h.client.get(path)).json() == [str(no_node.id)]
    candidates = [await p4.create_user(f"fallback{i}") for i in range(6)]
    for candidate in candidates:
        await p4.users.update_interests(candidate.id, ("python",))
    await p4.add_block(candidates[0], actor)
    await p4.add_follow(actor, candidates[1], "pending")
    await p4.add_follow(actor, candidates[2], "accepted")
    await p4.users.update_account_status(candidates[3].id, "suspended")
    await p4.users.update_interests(candidates[5].id, ("python", "música"))
    response = await p4.h.client.get(path)
    assert response.status_code == 200
    expected = [str(candidates[5].id)] + sorted([str(candidates[4].id), str(no_node.id)])
    assert response.json() == expected
