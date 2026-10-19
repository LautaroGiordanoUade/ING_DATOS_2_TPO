from app.domain.entities import Comment


def comment_to_document(comment: Comment) -> dict[str, object]:
    return {
        "_id": str(comment.id),
        "post_id": str(comment.post_id),
        "user_id": str(comment.user_id),
        "text": comment.text,
        "created_at": comment.created_at,
    }