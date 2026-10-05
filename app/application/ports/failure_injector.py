from dataclasses import dataclass
from typing import Protocol


class InjectedFailureError(RuntimeError):
    pass


class FailureInjector(Protocol):
    async def checkpoint(self, step: str) -> None: ...


class NoOpFailureInjector:
    async def checkpoint(self, step: str) -> None:
        del step


@dataclass(slots=True)
class ConfigurableFailureInjector:
    fail_at: str

    async def checkpoint(self, step: str) -> None:
        if step == self.fail_at:
            raise InjectedFailureError(f"Falla de demostración inyectada en '{step}'")

