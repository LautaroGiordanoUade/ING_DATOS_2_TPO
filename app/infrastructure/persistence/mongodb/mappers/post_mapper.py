from app.domain.entities import Post


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

