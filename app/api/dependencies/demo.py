from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings


def demo_mode_enabled() -> bool:
    settings = get_settings()
    return settings.app_demo_mode and settings.app_env in {"development", "testing"}


DemoModeDep = Annotated[bool, Depends(demo_mode_enabled)]
