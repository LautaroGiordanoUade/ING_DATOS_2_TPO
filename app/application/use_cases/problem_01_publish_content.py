from uuid import UUID

from app.application.services import CompensationService, OperationContext, OperationStep
from app.domain.entities import Post
from app.domain.repositories import FeedRepository, PostRepository, SocialGraphRepository


class PublishContentUseCase:
    def __init__(
        self,
        posts: PostRepository,
        graph: SocialGraphRepository,
        feeds: FeedRepository,
        compensation: CompensationService,
    ) -> None:
        self._posts = posts
        self._graph = graph
        self._feeds = feeds
        self._compensation = compensation

    async def execute(self, post: Post) -> OperationContext:
        followers: tuple[UUID, ...] = ()

        async def create_post() -> None:
            await self._posts.create(post)

        async def delete_post() -> None:
            # TODO(TP): Validar si borrar es la compensación adecuada o usar tombstone.
            await self._posts.delete(post.id)

        async def load_followers() -> None:
            nonlocal followers
            followers = await self._graph.follower_ids(post.user_id)

        async def fan_out() -> None:
            # TODO(TP): Elegir fan-out síncrono, diferido o híbrido para cuentas masivas.
            await self._feeds.add_to_feeds(followers, post.id, post.published_at.timestamp())

        async def remove_from_feeds() -> None:
            # TODO(TP): Implementar compensación exacta e idempotente del fan-out.
            await self._feeds.remove_from_feeds(post.id)

        operation = OperationContext(operation_type="problem_01_publish_content")
        return await self._compensation.execute(
            operation,
            (
                OperationStep("mongo_create_post", create_post, delete_post),
                OperationStep("neo4j_load_followers", load_followers),
                OperationStep("redis_feed_update", fan_out, remove_from_feeds),
            ),
        )
