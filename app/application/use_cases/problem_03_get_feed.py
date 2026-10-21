import asyncio
from dataclasses import asdict
from datetime import UTC
from uuid import UUID

from app.application.ports.personalized_feed import FeedAudience, PersonalizedFeedStore
from app.application.services.feed_page import FeedPosition, FeedSession, FeedWindow
from app.core.exceptions import InvalidOperationError
from app.domain.counter_names import POST_COMMENTS, POST_REACTIONS
from app.domain.entities import Post
from app.domain.repositories import CounterRepository, PostRepository
from app.infrastructure.security.feed_cursor import FeedCursorCodec


class GetFeedUseCase:
    def __init__(
        self,
        feeds: PersonalizedFeedStore,
        posts: PostRepository,
        counters: CounterRepository,
        audience: FeedAudience,
    ) -> None:
        self._feeds, self._posts, self._counters, self._audience = feeds, posts, counters, audience
        self._codec = FeedCursorCodec()

    @staticmethod
    def _timestamp(post: Post) -> float:
        date = post.published_at
        return (date if date.tzinfo else date.replace(tzinfo=UTC)).timestamp()

    async def _posts_for(self, user_id: UUID, ids: tuple[UUID, ...]) -> tuple[Post, ...]:
        if not ids:
            return ()
        posts = await self._posts.get_many(ids)
        allowed, visible = await asyncio.gather(
            self._audience.eligible_authors(user_id, tuple({post.user_id for post in posts})),
            self._feeds.visible(user_id, tuple(post.id for post in posts)),
        )
        return tuple(post for post in posts if post.user_id in allowed and post.id in visible)

    async def _counts(self, posts: tuple[Post, ...]) -> tuple[dict[UUID, int], dict[UUID, int]]:
        ids = tuple(post.id for post in posts)
        reactions, comments = await asyncio.gather(
            self._counters.get_many(POST_REACTIONS, ids),
            self._counters.get_many(POST_COMMENTS, ids),
        )
        return reactions, comments

    async def _window(self, session: FeedSession, index: int) -> FeedWindow:
        existing = await self._feeds.window(session, index)
        if existing is not None:
            return existing
        score, identifier = session.anchor, "~"
        if index:
            previous = await self._feeds.window(session, index - 1)
            if previous is None or not previous.more:
                raise InvalidOperationError("Cursor de feed sin bloque anterior")
            score, identifier = previous.boundary_score, previous.boundary_id
        candidates = await self._feeds.candidates(session.user_id, score, identifier)
        ids = tuple(post_id for post_id, _ in candidates.rows)
        posts = await self._posts_for(session.user_id, ids)
        reactions, comments = await self._counts(posts)
        ranked = sorted(
            posts,
            key=lambda post: (
                self._timestamp(post)
                + 60
                * min(60, max(0, reactions.get(post.id, 0)) + 2 * max(0, comments.get(post.id, 0))),
                self._timestamp(post),
                str(post.id),
            ),
            reverse=True,
        )
        if candidates.rows:
            last_id, score = candidates.rows[-1]
            identifier = str(last_id)
        return await self._feeds.save_window(
            session,
            index,
            FeedWindow(
                ids=[post.id for post in ranked],
                boundary_score=score,
                boundary_id=identifier,
                more=candidates.more,
            ),
        )

    async def execute(self, user_id: UUID, cursor: str | None = None) -> dict[str, object]:
        if cursor is None:
            session = await self._feeds.start(user_id)
            position = FeedPosition(session_id=session.id, user_id=user_id, expires=session.expires)
        else:
            position = self._codec.decode(cursor, user_id)
            session = await self._feeds.session(position.session_id)
            if session.user_id != user_id or session.expires != position.expires:
                raise InvalidOperationError("Cursor de feed inconsistente")
        items: list[dict[str, object]] = []
        more = True
        for _ in range(10):
            window = await self._window(session, position.window)
            if position.offset > len(window.ids):
                raise InvalidOperationError("Posicion de cursor invalida")
            posts = await self._posts_for(user_id, tuple(window.ids[position.offset :]))
            reactions, comments = await self._counts(posts)
            current = await self._posts_for(user_id, tuple(post.id for post in posts))
            by_id = {post.id: post for post in current}
            for index in range(position.offset, len(window.ids)):
                post = by_id.get(window.ids[index])
                position.offset = index + 1
                if post is not None:
                    items.append(
                        {
                            **asdict(post),
                            "reaction_count": reactions.get(post.id, 0),
                            "comment_count": comments.get(post.id, 0),
                        }
                    )
                    if len(items) == 20:
                        break
            if position.offset == len(window.ids):
                more = window.more
                position.window += 1
                position.offset = 0
            if len(items) == 20 or not more:
                break
        return {"items": items, "next_cursor": self._codec.encode(position) if more else None}
