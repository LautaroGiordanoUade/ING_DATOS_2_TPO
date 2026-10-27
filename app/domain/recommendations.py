from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SuggestionCandidate:
    user_id: UUID
    connections: int


@dataclass(frozen=True)
class InterestProfile:
    user_id: UUID
    interests: tuple[str, ...]
