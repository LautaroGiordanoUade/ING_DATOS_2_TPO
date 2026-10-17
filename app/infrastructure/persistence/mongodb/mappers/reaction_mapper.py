from datetime import datetime
from typing import cast
from uuid import UUID

from app.domain.entities import Reaction


def document_to_reaction(document: dict[str, object]) -> Reaction:
    return Reaction(
        id=UUID(str(document["_id"])),
        post_id=UUID(str(document["post_id"])),
        user_id=UUID(str(document["user_id"])),
        kind=str(document["kind"]),
        created_at=cast(datetime, document["created_at"]),
    )