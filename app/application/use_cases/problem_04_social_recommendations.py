from uuid import UUID

from app.domain.repositories import SocialGraphRepository, UserRepository

_SUGGESTIONS_LIMIT = 10
_CANDIDATE_BATCH = 250


class SocialRecommendationsUseCase:
    def __init__(self, graph: SocialGraphRepository, users: UserRepository) -> None:
        self._graph = graph
        self._users = users

    async def mutual_friends(self, user_id: UUID, other_user_id: UUID) -> tuple[UUID, ...]:
        if user_id == other_user_id:
            return ()
        if await self._users.is_suspended(user_id) or await self._users.is_suspended(other_user_id):
            return ()
        candidates = await self._graph.get_mutual_friends(user_id, other_user_id)
        if not candidates:
            return ()
        return await self._users.active_ids(candidates)

    async def recommendations(self, user_id: UUID) -> tuple[UUID, ...]:
        actor = await self._users.get(user_id)
        if actor is None or actor.account_status != "active":
            return ()
        interests = set(actor.interests)
        # Keep only the best ten in memory, but evaluate every batch before ranking.
        # Limiting the old graph score to 30 would discard relevant interest matches.
        ranked: list[tuple[int, int, str, UUID]] = []
        after: UUID | None = None
        while True:
            candidates = await self._graph.suggestion_candidates(user_id, after, _CANDIDATE_BATCH)
            if not candidates:
                break
            scores = {row.user_id: row.connections for row in candidates}
            profiles = await self._users.interest_profiles(tuple(scores))
            for profile in profiles:
                shared = len(interests.intersection(profile.interests))
                ranked.append(
                    (-shared, -scores[profile.user_id], str(profile.user_id), profile.user_id)
                )
            ranked = sorted(ranked)[:_SUGGESTIONS_LIMIT]
            after = candidates[-1].user_id
            if len(candidates) < _CANDIDATE_BATCH:
                break
        result = [row[3] for row in ranked]
        if len(result) == _SUGGESTIONS_LIMIT or not interests:
            return tuple(result)

        # Only fill remaining slots after exhausting eligible second-degree accounts.
        fallback: list[tuple[int, str, UUID]] = []
        after = None
        while True:
            profiles = await self._users.interest_candidates(
                actor.interests, after, _CANDIDATE_BATCH
            )
            if not profiles:
                break
            eligible = await self._graph.eligible_suggestions(
                user_id, tuple(profile.user_id for profile in profiles)
            )
            for profile in profiles:
                if profile.user_id in eligible and profile.user_id not in result:
                    shared = len(interests.intersection(profile.interests))
                    fallback.append((-shared, str(profile.user_id), profile.user_id))
            fallback = sorted(fallback)[: _SUGGESTIONS_LIMIT - len(result)]
            after = profiles[-1].user_id
            if len(profiles) < _CANDIDATE_BATCH:
                break
        return tuple(result + [row[2] for row in fallback])
