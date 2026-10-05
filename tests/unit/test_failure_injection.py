import pytest

from app.application.ports import (
    ConfigurableFailureInjector,
    InjectedFailureError,
    NoOpFailureInjector,
)


@pytest.mark.asyncio
async def test_configurable_injector_fails_only_at_selected_checkpoint() -> None:
    injector = ConfigurableFailureInjector("redis_feed_update")
    await injector.checkpoint("mongo_create_post")
    with pytest.raises(InjectedFailureError):
        await injector.checkpoint("redis_feed_update")


@pytest.mark.asyncio
async def test_noop_injector_never_fails() -> None:
    await NoOpFailureInjector().checkpoint("any_step")

