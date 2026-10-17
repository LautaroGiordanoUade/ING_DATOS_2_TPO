from datetime import datetime
from typing import cast
from uuid import UUID

from app.domain.entities import Post
from app.domain.entities.models import ModerationStatus


def post_to_document(post: Post) -> dict[str, object]:
    return {
        "_id": str(post.id),
        "user_id": str(post.user_id),
        "text": post.text,
        "media": list(post.media),
        "content_type": post.content_type,
        "visibility": post.visibility,
        "interests": list(post.interests),
        "moderation_status": post.moderation_status.value,
        "published_at": post.published_at,
    }


def document_to_post(document: dict[str, object]) -> Post:
    return Post(
        id=UUID(str(document["_id"])),
        user_id=UUID(str(document["user_id"])),
        text=str(document["text"]),
        media=tuple(cast(list[str], document.get("media", []))),
        content_type=str(document.get("content_type", "text")),
        visibility=str(document.get("visibility", "public")),
        interests=tuple(cast(list[str], document.get("interests", []))),
        moderation_status=ModerationStatus(str(document["moderation_status"])),
        published_at=cast(datetime, document["published_at"]),
    )