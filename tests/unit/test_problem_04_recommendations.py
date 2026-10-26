from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.problem_04_social_recommendations import (
    SocialRecommendationsUseCase,
)


class FakeGraphRepository:
    def __init__(self) -> None:
        self.mutual: tuple[UUID, ...] = ()
        self.suggested: tuple[UUID, ...] = ()
        self.last_limit: int | None = None

    async def get_mutual_friends(self, user_id: UUID, other_user_id: UUID) -> tuple[UUID, ...]:
        return self.mutual

    async def get_suggested_accounts(self, user_id: UUID, limit: int) -> tuple[UUID, ...]:
        self.last_limit = limit
        return self.suggested[:limit]

    async def follow(self, user_id: UUID, followed_user_id: UUID) -> None:
        pass

    async def unfollow(self, user_id: UUID, followed_user_id: UUID) -> None:
        pass

    async def follower_ids(self, user_id: UUID) -> tuple[UUID, ...]:
        return ()

    async def trace_relationships(self, user_id: UUID) -> dict[str, object]:
        return {}


class FakeUserRepository:
    def __init__(self) -> None:
        self.suspended_ids: set[UUID] = set()
        self.active_ids_calls: int = 0

    async def is_suspended(self, user_id: UUID) -> bool:
        return user_id in self.suspended_ids

    async def active_ids(self, user_ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
        self.active_ids_calls += 1
        return tuple(uid for uid in user_ids if uid not in self.suspended_ids)

    async def by_username(self, username: str) -> Any:
        return None

    async def get(self, user_id: UUID) -> Any:
        return None

    async def create(self, user: Any) -> Any:
        return user

    async def update_account_status(self, user_id: UUID, status: str) -> None:
        pass


@pytest.mark.asyncio
async def test_mutual_friends_same_user_returns_empty() -> None:
    graph = FakeGraphRepository()
    users = FakeUserRepository()
    use_case = SocialRecommendationsUseCase(graph, users)
    user_id = uuid4()

    result = await use_case.mutual_friends(user_id, user_id)
    assert result == ()
    assert users.active_ids_calls == 0


@pytest.mark.asyncio
async def test_mutual_friends_suspended_requester_returns_empty() -> None:
    graph = FakeGraphRepository()
    users = FakeUserRepository()
    use_case = SocialRecommendationsUseCase(graph, users)
    u1, u2, friend = uuid4(), uuid4(), uuid4()
    graph.mutual = (friend,)
    users.suspended_ids.add(u1)

    result = await use_case.mutual_friends(u1, u2)
    assert result == ()


@pytest.mark.asyncio
async def test_mutual_friends_suspended_target_returns_empty() -> None:
    graph = FakeGraphRepository()
    users = FakeUserRepository()
    use_case = SocialRecommendationsUseCase(graph, users)
    u1, u2, friend = uuid4(), uuid4(), uuid4()
    graph.mutual = (friend,)
    users.suspended_ids.add(u2)

    result = await use_case.mutual_friends(u1, u2)
    assert result == ()


@pytest.mark.asyncio
async def test_mutual_friends_filters_suspended_candidates() -> None:
    graph = FakeGraphRepository()
    users = FakeUserRepository()
    use_case = SocialRecommendationsUseCase(graph, users)
    u1, u2 = uuid4(), uuid4()
    f1, f2 = uuid4(), uuid4()
    graph.mutual = (f1, f2)
    users.suspended_ids.add(f2)

    result = await use_case.mutual_friends(u1, u2)
    assert result == (f1,)


@pytest.mark.asyncio
async def test_mutual_friends_empty_graph_skips_active_ids_lookup() -> None:
    graph = FakeGraphRepository()
    users = FakeUserRepository()
    use_case = SocialRecommendationsUseCase(graph, users)
    u1, u2 = uuid4(), uuid4()

    result = await use_case.mutual_friends(u1, u2)
    assert result == ()
    assert users.active_ids_calls == 0


@pytest.mark.asyncio
async def test_recommendations_suspended_user_returns_empty() -> None:
    graph = FakeGraphRepository()
    users = FakeUserRepository()
    use_case = SocialRecommendationsUseCase(graph, users)
    user_id = uuid4()
    users.suspended_ids.add(user_id)
    graph.suggested = (uuid4(), uuid4())

    result = await use_case.recommendations(user_id)
    assert result == ()


@pytest.mark.asyncio
async def test_recommendations_filters_suspended_candidates() -> None:
    graph = FakeGraphRepository()
    users = FakeUserRepository()
    use_case = SocialRecommendationsUseCase(graph, users)
    user_id = uuid4()
    c1, c2 = uuid4(), uuid4()
    graph.suggested = (c1, c2)
    users.suspended_ids.add(c1)

    result = await use_case.recommendations(user_id)
    assert result == (c2,)


@pytest.mark.asyncio
async def test_recommendations_oversamples_and_caps_at_ten_after_filtering() -> None:
    graph = FakeGraphRepository()
    users = FakeUserRepository()
    use_case = SocialRecommendationsUseCase(graph, users)
    user_id = uuid4()
    candidates = tuple(uuid4() for _ in range(15))
    graph.suggested = candidates
    users.suspended_ids.update(candidates[:3])

    result = await use_case.recommendations(user_id)
    assert graph.last_limit == 30
    assert len(result) == 10
    assert result == candidates[3:13]
