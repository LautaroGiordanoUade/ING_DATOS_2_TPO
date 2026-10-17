#Guardar o cambiar la reacción de alguien, y quitársela
from typing import Protocol
from uuid import UUID

from app.domain.entities import Reaction


class ReactionRepository(Protocol):
    async def upsert(self, reaction: Reaction) -> Reaction | None:
        """Guarda la reacción. Devuelve la que había antes, o None si era la primera."""
        ...

    async def delete_for_user(self, post_id: UUID, user_id: UUID) -> Reaction | None:
        """Borra la reacción. Devuelve la que se borró, o None si no había nada."""
        ...