from datetime import datetime
from typing import cast
from uuid import UUID

from app.domain.entities import Comment


def comment_to_document(comment: Comment) -> dict[str, object]:
    return {
        "_id": str(comment.id),
        "post_id": str(comment.post_id),
        "user_id": str(comment.user_id),
        "text": comment.text,
        "created_at": comment.created_at,
    }


def document_to_comment(document: dict[str, object]) -> Comment:
    return Comment(
        id=UUID(str(document["_id"])),
        post_id=UUID(str(document["post_id"])),
        user_id=UUID(str(document["user_id"])),
        text=str(document["text"]),
        created_at=cast(datetime, document["created_at"]),
    )
