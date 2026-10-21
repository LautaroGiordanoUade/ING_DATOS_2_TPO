from typing import Any, cast
from uuid import uuid4

import pytest

from app.application.use_cases import FollowUserUseCase
from app.core.exceptions import InvalidOperationError


@pytest.mark.asyncio
async def test_user_cannot_follow_itself() -> None:
    dependency = cast(Any, object())
    use_case = FollowUserUseCase(
        dependency,
        dependency,
        dependency,
        dependency,
    )
    user_id = uuid4()
    with pytest.raises(InvalidOperationError):
        await use_case.follow(user_id, user_id)

