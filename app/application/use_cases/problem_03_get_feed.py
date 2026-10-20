from dataclasses import asdict
from uuid import UUID

from app.domain.counter_names import POST_COMMENTS, POST_REACTIONS
from app.domain.repositories import CounterRepository, FeedRepository, PostRepository
from app.domain.value_objects import FeedCursor


class GetFeedUseCase:
    def __init__(
        self, feeds: FeedRepository, posts: PostRepository, counters: CounterRepository
    ) -> None:
        self._feeds = feeds
        self._posts = posts
        self._counters = counters

    async def execute(self, user_id: UUID, cursor: FeedCursor | None = None) -> object:
        page = await self._feeds.get_feed(user_id, cursor, 20)
        posts = await self._posts.get_many(page.items)
        ids = tuple(post.id for post in posts)
        reactions = await self._counters.get_many(POST_REACTIONS, ids)
        comments = await self._counters.get_many(POST_COMMENTS, ids)
        return {
            "items": [
                {
                    **asdict(post),
                    "reaction_count": reactions.get(post.id, 0),
                    "comment_count": comments.get(post.id, 0),
                }
                for post in posts
            ],
            "next_cursor": None,
        }
