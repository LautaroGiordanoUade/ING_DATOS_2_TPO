"""Authenticated own-reaction reads against real MongoDB and account/post filters."""

import os
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.domain.entities import Reaction
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoReactionRepository,
)
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB and Redis"
)


async def test_own_reaction_is_scoped_to_bearer(harness: Harness) -> None:
    h = harness
    reactions = MongoReactionRepository(h.resources.mongo_client[get_settings().mongodb_database])
    await reactions.upsert(Reaction(post_id=h.post.id, user_id=h.user.id, kind="aplauso"))
    await reactions.upsert(Reaction(post_id=h.post.id, user_id=h.moderator.id, kind="love"))
    path = f"/api/v1/interactions/reactions/{h.post.id}/me"
    response = await h.client.get(path, headers=h.headers())
    assert response.status_code == 200
    assert response.json() == {"kind": "aplauso"}
    other = await h.client.get(path, headers=h.headers(h.moderator))
    assert other.json() == {"kind": "love"}
    # Supplying someone else's UUID cannot select their reaction.
    missing = await h.client.get(
        path + f"?user_id={h.user.id}", headers=h.headers(h.admin)
    )
    assert missing.json() == {"kind": None}
    await reactions.delete_for_user(h.post.id, h.user.id)
    assert (await h.client.get(path, headers=h.headers())).json() == {"kind": None}


@pytest.mark.parametrize("credential", [None, "invalid"])
async def test_own_reaction_requires_login(harness: Harness, credential: str | None) -> None:
    response = await harness.client.get(
        f"/api/v1/interactions/reactions/{harness.post.id}/me",
        headers={} if credential is None else {"Authorization": f"Bearer {credential}"},
    )
    assert response.status_code == 401


async def test_own_reaction_respects_post_availability(harness: Harness) -> None:
    h = harness
    missing = await h.client.get(
        f"/api/v1/interactions/reactions/{uuid4()}/me", headers=h.headers()
    )
    assert missing.status_code == 404
    await h.run(await h.decision(await h.report()))
    hidden = await h.client.get(
        f"/api/v1/interactions/reactions/{h.post.id}/me", headers=h.headers()
    )
    assert hidden.status_code == 404
