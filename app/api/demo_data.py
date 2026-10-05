from datetime import UTC, datetime
from uuid import UUID

from app.schemas.models import (
    FeedResponse,
    MessageResponse,
    PostResponse,
    UserResponse,
    UserTraceResponse,
)

DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
DEMO_OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
DEMO_POST_ID = UUID("10000000-0000-0000-0000-000000000001")
DEMO_OPERATION_ID = UUID("90000000-0000-0000-0000-000000000001")
DEMO_MESSAGE_ID = UUID("30000000-0000-0000-0000-000000000001")
DEMO_CONVERSATION_ID = UUID("20000000-0000-0000-0000-000000000001")
DEMO_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def demo_post(user_id: UUID = DEMO_USER_ID) -> PostResponse:
    return PostResponse(
        id=DEMO_POST_ID,
        user_id=user_id,
        text="Publicación de demostración: reemplazar mediante TODO(TP).",
        media=[],
        interests=["data-engineering", "fastapi"],
        published_at=DEMO_TIME,
        reaction_count=7,
        comment_count=3,
    )


def demo_user(user_id: UUID = DEMO_USER_ID) -> UserResponse:
    return UserResponse(
        id=user_id,
        username="demo_user",
        full_name="Usuario Demo",
        biography="Perfil temporal para probar la API.",
        account_type="public",
        account_status="active",
        registered_at=DEMO_TIME,
    )


def demo_message(sender_id: UUID = DEMO_USER_ID) -> MessageResponse:
    return MessageResponse(
        id=DEMO_MESSAGE_ID,
        conversation_id=DEMO_CONVERSATION_ID,
        sender_id=sender_id,
        text="Mensaje de demostración.",
        read_by={sender_id},
        created_at=DEMO_TIME,
    )


def demo_feed(user_id: UUID) -> FeedResponse:
    return FeedResponse(items=[demo_post(user_id)], next_cursor=None)


def demo_trace(user_id: UUID) -> UserTraceResponse:
    return UserTraceResponse(
        user_id=user_id,
        profile=demo_user(user_id),
        relationships={
            "followers": [str(DEMO_OTHER_USER_ID)],
            "following": [],
            "source": "mock-development-only",
        },
        recent_posts=[demo_post(user_id)],
        active_conversations=[
            {
                "conversation_id": str(DEMO_CONVERSATION_ID),
                "participant_ids": [str(user_id), str(DEMO_OTHER_USER_ID)],
            }
        ],
    )
