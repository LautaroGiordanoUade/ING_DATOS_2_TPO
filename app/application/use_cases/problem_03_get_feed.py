from uuid import UUID

from app.core.exceptions import FeatureNotImplementedError
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
        # TODO(TP): Integrar 20 IDs de Redis, documentos Mongo y contadores sin N+1.
        # TODO(TP): Definir ranking y semántica exacta del cursor hacia atrás.
        raise FeatureNotImplementedError("Problema 3: feed personalizado")

