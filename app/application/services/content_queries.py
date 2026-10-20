from dataclasses import asdict
from uuid import UUID

from app.core.exceptions import ResourceNotFoundError
from app.domain.counter_names import POST_COMMENTS, POST_REACTIONS
from app.domain.entities import Post
from app.domain.repositories import CounterRepository, PostRepository


class ContentQueries:
    def __init__(self, posts: PostRepository, counters: CounterRepository) -> None:
        self._posts, self._counters = posts, counters

    async def _responses(self, posts: tuple[Post, ...]) -> list[dict[str, object]]:
        ids = tuple(post.id for post in posts)
        reactions = await self._counters.get_many(POST_REACTIONS, ids)
        comments = await self._counters.get_many(POST_COMMENTS, ids)
        return [
            {
                **asdict(post),
                "reaction_count": reactions.get(post.id, 0),
                "comment_count": comments.get(post.id, 0),
            }
            for post in posts
        ]

    async def detail(self, post_id: UUID) -> dict[str, object]:
        post = await self._posts.get(post_id)
        if post is None or post.visibility != "public":
            raise ResourceNotFoundError("Public post not found")
        return (await self._responses((post,)))[0]

    async def by_author(self, user_id: UUID) -> list[dict[str, object]]:
        return await self._responses(await self._posts.list_recent_by_user(user_id, 100))
