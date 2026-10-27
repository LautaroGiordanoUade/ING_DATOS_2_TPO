"""Deterministic business fixtures, independent of persistence and wall-clock time."""

import hashlib
import json
import random
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

START = datetime(2026, 10, 1, tzinfo=UTC)
TOPICS = ("datos", "python", "astronomia", "fotografia", "ciclismo", "cocina")
NAMES = ("Sofía", "Mateo", "Valentina", "Nicolás", "Camila", "Tomás", "Lucía", "Martín")
SURNAMES = ("García", "López", "Pérez", "Romero", "Fernández", "Torres", "Díaz")


@dataclass(frozen=True)
class SeedOptions:
    users: int = 1200
    posts: int = 50_000
    comments: int = 15_000
    reactions: int = 30_000
    messages: int = 10_000
    conversations: int = 120
    reports: int = 24
    seed: int = 42
    batch_size: int = 500

    def __post_init__(self) -> None:
        if not 6 <= self.users <= 10_000:
            raise ValueError("users debe estar entre 6 y 10000")
        if not 1 <= self.posts <= 500_000 or not 1 <= self.conversations <= self.users:
            raise ValueError("posts debe estar entre 1 y 500000; conversations entre 1 y users")
        if min(self.comments, self.reactions, self.messages, self.reports) < 0:
            raise ValueError("Las cantidades no pueden ser negativas")
        if max(self.comments, self.reactions, self.messages) > 500_000:
            raise ValueError("El máximo por entidad es 500000")
        if self.reactions > self.posts * (self.users - 1) or self.reports > self.posts:
            raise ValueError("Reacciones/reportes exceden la cantidad de pares disponibles")
        if not 1 <= self.batch_size <= 2000 or not 0 <= self.seed <= 1_000_000:
            raise ValueError("batch_size debe estar entre 1 y 2000; seed entre 0 y 1000000")


class Dataset:
    def __init__(self, options: SeedOptions) -> None:
        self.options = options
        self.name = f"tpo-v1-{options.seed}"
        self.namespace = uuid5(NAMESPACE_URL, f"niche-social/{self.name}")
        self.users = [self.identifier("user", i) for i in range(options.users)]
        self.posts = [self.identifier("post", i) for i in range(options.posts)]
        self.groups = [self.identifier("group", i) for i in range(options.conversations)]

    def identifier(self, kind: str, index: int) -> str:
        return str(uuid5(self.namespace, f"{kind}:{index}"))

    def config(self) -> dict[str, int]:
        return {k: v for k, v in asdict(self.options).items() if k != "batch_size"}

    def private(self, index: int) -> bool:
        return index == 2 or index > 4 and index % 5 == 0

    def author_index(self, post: int) -> int:
        return post % self.options.users

    def user_documents(self) -> Iterator[dict[str, Any]]:
        rng = random.Random(f"{self.name}:users")
        for i, identifier in enumerate(self.users):
            yield {
                "_id": identifier,
                "seed_dataset": self.name,
                "username": f"tpo{self.options.seed}_{i:04d}",
                "full_name": f"{rng.choice(NAMES)} {rng.choice(SURNAMES)}",
                "email": f"tpo{self.options.seed}_{i:04d}@example.test",
                "biography": f"Comunidad de {TOPICS[i % len(TOPICS)]}. Datos sintéticos del TPO.",
                "account_type": "private" if self.private(i) else "public",
                "account_status": "active",
                "auth_version": 0,
                "role": "moderator" if i == 3 else "admin" if i == 4 else "user",
                "registered_at": START - timedelta(days=365 - i % 300),
                "interests": [TOPICS[i % len(TOPICS)], TOPICS[(i + 1) % len(TOPICS)]],
            }

    def relationships(self) -> list[dict[str, str]]:
        pairs = {(i, 0) for i in range(1, self.options.users)}
        pairs |= {(1, i) for i in range(self.options.users) if i != 1}
        for i in range(self.options.users):
            for offset in range(1, min(9, self.options.users)):
                pairs.add((i, (i + offset) % self.options.users))
        # A real blocked pair has no simultaneous FOLLOWS edge.
        blocked = {(2, 5)}
        return [
            {
                "f": self.users[f],
                "a": self.users[a],
                "kind": "FOLLOWS",
                "status": "pending" if self.private(a) and (f + a) % 3 == 0 else "accepted",
            }
            for f, a in sorted(pairs)
            if (f, a) not in blocked and (a, f) not in blocked
        ]

    def blocks(self) -> list[dict[str, str]]:
        return [{"f": self.users[2], "a": self.users[5], "kind": "BLOCKS", "status": "blocked"}]

    def post_documents(self) -> Iterator[dict[str, Any]]:
        rng = random.Random(f"{self.name}:posts")
        phrases = (
            "Comparto una experiencia",
            "Consulta para la comunidad",
            "Aprendizajes del día",
            "Guía práctica",
            "Resultados de mi proyecto",
            "Recomendaciones para empezar",
        )
        for i, identifier in enumerate(self.posts):
            author = self.author_index(i)
            topic = TOPICS[author % len(TOPICS)]
            yield {
                "_id": identifier,
                "seed_dataset": self.name,
                "user_id": self.users[author],
                "text": (
                    f"{rng.choice(phrases)} sobre {topic}. Conversación #{i + 1} de la comunidad."
                ),
                "media": [],
                "content_type": "text",
                "visibility": "public",
                "interests": [topic],
                "moderation_status": "approved",
                "publication_state": "published",
                "published_at": START + timedelta(seconds=i * 30),
            }

    def interaction_documents(self, kind: str, count: int) -> Iterator[dict[str, Any]]:
        rng = random.Random(f"{self.name}:{kind}")
        for i in range(count):
            # A modular permutation produces unique reaction (post,user) pairs, even beyond posts.
            p = i % self.options.posts
            author = self.author_index(p)
            actor = (
                author + 1 + (i // self.options.posts) % (self.options.users - 1)
            ) % self.options.users
            doc = {
                "_id": self.identifier(kind, i),
                "seed_dataset": self.name,
                "post_id": self.posts[p],
                "user_id": self.users[actor],
                "created_at": START + timedelta(seconds=p * 30 + 5 + i // self.options.posts),
            }
            if kind == "reaction":
                doc["kind"] = rng.choice(("like", "love", "wow"))
            else:
                phrase = rng.choice(
                    ("Gracias por compartir", "Muy buen aporte", "Me interesa conocer más")
                )
                doc["text"] = f"{phrase}. Comentario {i + 1}."
            yield doc

    def members(self, group: int) -> list[str]:
        return [
            self.users[(group * 7 + offset) % self.options.users]
            for offset in range(min(3 + group % 6, self.options.users))
        ]

    def group_documents(self) -> Iterator[dict[str, Any]]:
        for i, identifier in enumerate(self.groups):
            members = self.members(i)
            count = (
                self.options.messages + self.options.conversations - 1 - i
            ) // self.options.conversations
            yield {
                "_id": identifier,
                "seed_dataset": self.name,
                "creator_id": members[0],
                "participant_ids": members,
                "name": f"Comunidad {TOPICS[i % len(TOPICS)]} {i + 1}",
                "request_key": f"{self.name}:group:{i}",
                "sequence": count,
                "read_through": {actor: max(0, count - n * 3) for n, actor in enumerate(members)},
                "created_at": START - timedelta(days=1),
                "redis_pending": False,
            }

    def message_documents(self) -> Iterator[dict[str, Any]]:
        for i in range(self.options.messages):
            group = i % self.options.conversations
            sequence = i // self.options.conversations + 1
            members = self.members(group)
            yield {
                "_id": self.identifier("message", i),
                "seed_dataset": self.name,
                "conversation_id": self.groups[group],
                "sender_id": members[(sequence - 1) % len(members)],
                "text": f"Intercambio {sequence}: ideas sobre {TOPICS[group % len(TOPICS)]}.",
                "sequence": sequence,
                "request_key": f"{self.name}:message:{i}",
                "created_at": START + timedelta(seconds=i * 5),
                "delivery_status": "completed",
                "completed_steps": ["mongo_persist", "redis_distribution"],
                "error": None,
            }

    def report_documents(self) -> Iterator[dict[str, Any]]:
        for i in range(self.options.reports):
            p = i % self.options.posts
            author = self.author_index(p)
            yield {
                "_id": self.identifier("report", i),
                "seed_dataset": self.name,
                "post_id": self.posts[p],
                "reporter_id": self.users[(author + 1) % self.options.users],
                "reason": "spam" if i % 2 else "other",
                "description": f"Revisar publicación de ejemplo {i + 1}.",
                "target_type": "post",
                "resolution_status": "pending",
                "moderator_id": None,
                "reported_at": START + timedelta(seconds=p * 30 + 10),
                "resolved_at": None,
            }

    def documents(self) -> dict[str, Iterator[dict[str, Any]]]:
        return {
            "users": self.user_documents(),
            "posts": self.post_documents(),
            "comments": self.interaction_documents("comment", self.options.comments),
            "reactions": self.interaction_documents("reaction", self.options.reactions),
            "conversations": self.group_documents(),
            "messages": self.message_documents(),
            "moderation_reports": self.report_documents(),
        }

    def checksum(self) -> str:
        digest = hashlib.sha256()
        for name, docs in self.documents().items():
            digest.update(name.encode())
            for doc in docs:
                digest.update(
                    json.dumps(doc, default=str, sort_keys=True, ensure_ascii=True).encode()
                )
        for edge in self.relationships() + self.blocks():
            digest.update(json.dumps(edge, sort_keys=True).encode())
        return digest.hexdigest()

    def summary(self) -> dict[str, Any]:
        return {
            "dataset": self.name,
            "options": self.config(),
            "sha256": self.checksum(),
            "meets_50000_posts": self.options.posts >= 50_000,
            "relationships": len(self.relationships()),
            "accounts": [
                {
                    "id": u["_id"],
                    "username": u["username"],
                    "role": u["role"],
                    "account_type": u["account_type"],
                }
                for u in list(self.user_documents())[:6]
            ],
            "example_post_id": self.posts[0],
            "example_conversation_id": self.groups[0],
        }
