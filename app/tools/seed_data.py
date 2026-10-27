"""Run explicitly with python -m app.tools.seed_data; default is a read-only plan."""

import argparse
import asyncio
import json
import os
import time
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path
from typing import Any
from uuid import uuid5

from pymongo import UpdateOne

from app.core.config import Settings, get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.indexes import ensure_mongo_indexes
from app.infrastructure.persistence.neo4j.client import create_neo4j_driver
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.security.password import PasswordHasher
from app.tools.dataset import Dataset, SeedOptions


@contextmanager
def dataset_lock(dataset: Dataset) -> Iterator[None]:
    # Same Linux host/shared interaction_locks volume as the supported deployment.
    import fcntl

    directory = Path(os.environ.get("INTERACTION_LOCK_DIR", "/home/appuser/interaction-locks"))
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"seed-{dataset.namespace}.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Otra carga de este dataset está en ejecución") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class DatasetStore:
    def __init__(self, settings: Settings, dataset: Dataset) -> None:
        self.dataset = dataset
        self.mongo = create_mongo_client(settings.mongodb_url)
        self.db: Any = self.mongo[settings.mongodb_database]
        self.redis: Any = create_redis_client(settings.redis_url)
        self.graph = create_neo4j_driver(
            settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
        )

    async def close(self) -> None:
        await self.mongo.close()
        await self.redis.aclose()
        await self.graph.close()

    async def preflight(self) -> None:
        await self.mongo.admin.command("ping")
        await self.redis.ping()
        await self.graph.verify_connectivity()
        users = list(self.dataset.user_documents())
        collision = await self.db.users.find_one(
            {
                "seed_dataset": {"$ne": self.dataset.name},
                "$or": [
                    {"_id": {"$in": self.dataset.users}},
                    {"username": {"$in": [u["username"] for u in users]}},
                    {"email": {"$in": [u["email"] for u in users]}},
                ],
            }
        )
        if collision:
            raise RuntimeError("Un UUID/username/email del dataset ya pertenece a otra cuenta")
        async with self.graph.session() as session:
            result = await session.run(
                "MATCH (u:User) WHERE u.id IN $ids AND coalesce(u.seed_dataset,'') <> $name "
                "RETURN count(u) AS n",
                ids=self.dataset.users,
                name=self.dataset.name,
            )
            record = await result.single(strict=True)
            if record["n"]:
                raise RuntimeError("Un UUID del dataset ya pertenece a otro nodo Neo4j")

    async def load(self, password: str) -> dict[str, Any]:
        with dataset_lock(self.dataset):
            await self.preflight()
            manifest = await self.db.seed_datasets.find_one({"_id": self.dataset.name})
            summary = self.dataset.summary()
            if manifest and manifest["config"] != self.dataset.config():
                raise RuntimeError("Esta semilla ya tiene otra configuración. Usá otra --seed.")
            if manifest and manifest["sha256"] != summary["sha256"]:
                raise RuntimeError(
                    "Cambió la versión del generador para esta semilla; usá otra --seed."
                )
            if manifest and manifest["status"] == "completed":
                # Never reset edits, credentials, reports or follow state after a demo.
                return {
                    **summary,
                    "status": "already_loaded",
                    "initial_verification": manifest["verification"],
                }
            if not password or len(password) < 12:
                raise ValueError("Definí SEED_PASSWORD con al menos 12 caracteres")
            existing = await self.db.users.find_one({"_id": self.dataset.users[0]})
            if existing and not await asyncio.to_thread(
                PasswordHasher().verify, password, existing["password_hash"]
            ):
                raise ValueError("Para reanudar, usá la misma SEED_PASSWORD de la carga incompleta")
            await ensure_mongo_indexes(self.db)
            await self.db.seed_datasets.update_one(
                {"_id": self.dataset.name},
                {
                    "$setOnInsert": {
                        "config": self.dataset.config(),
                        "sha256": summary["sha256"],
                        "status": "loading",
                        "created_at": datetime.now(UTC),
                    }
                },
                upsert=True,
            )
            digest = await asyncio.to_thread(PasswordHasher().hash, password)
            for name, docs in self.dataset.documents().items():
                for chunk in batched(docs, self.dataset.options.batch_size):
                    operations = []
                    for original in chunk:
                        doc = dict(original)
                        if name == "users":
                            doc["password_hash"] = digest
                        operations.append(
                            UpdateOne(
                                {"_id": doc["_id"], "seed_dataset": self.dataset.name},
                                {"$setOnInsert": doc},
                                upsert=True,
                            )
                        )
                    await self.db[name].bulk_write(operations, ordered=False)
                print(json.dumps({"phase": "mongo", "collection": name}), flush=True)
            await self.load_graph()
            await self.load_redis()
            verification = await self.verify()
            await self.db.seed_datasets.update_one(
                {"_id": self.dataset.name},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(UTC),
                        "verification": verification,
                    }
                },
            )
            return {**summary, "status": "completed", "verification": verification}

    async def load_graph(self) -> None:
        async with self.graph.session() as session:
            await (
                await session.run(
                    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE"
                )
            ).consume()
            rows = [
                {"id": u["_id"], "username": u["username"], "account_type": u["account_type"]}
                for u in self.dataset.user_documents()
            ]
            for chunk in batched(rows, self.dataset.options.batch_size):
                await (
                    await session.run(
                        "UNWIND $rows AS row MERGE (u:User {id:row.id}) "
                        "ON CREATE SET u.username=row.username, u.account_type=row.account_type, "
                        "u.account_status='active', u.seed_dataset=$name",
                        rows=list(chunk),
                        name=self.dataset.name,
                    )
                ).consume()
            for kind, edges in (
                ("FOLLOWS", self.dataset.relationships()),
                ("BLOCKS", self.dataset.blocks()),
            ):
                for chunk in batched(edges, self.dataset.options.batch_size):
                    await (
                        await session.run(
                            "UNWIND $rows AS row MATCH (f:User {id:row.f}), (a:User {id:row.a}) "
                            f"MERGE (f)-[r:{kind}]->(a) ON CREATE SET r.status=row.status, "
                            "r.seed_dataset=$name, r.created_at=$created",
                            rows=list(chunk),
                            name=self.dataset.name,
                            created="2026-09-30T00:00:00Z",
                        )
                    ).consume()
        print(json.dumps({"phase": "neo4j", "status": "loaded"}), flush=True)

    def views(
        self,
    ) -> tuple[dict[str, list[str]], dict[str, dict[str, float]], Counter[str], Counter[str]]:
        followers: dict[str, list[str]] = defaultdict(list)
        posts: dict[str, dict[str, float]] = defaultdict(dict)
        follower_counts: Counter[str] = Counter()
        following_counts: Counter[str] = Counter()
        for edge in self.dataset.relationships():
            if edge["status"] == "accepted":
                followers[edge["a"]].append(edge["f"])
                follower_counts[edge["a"]] += 1
                following_counts[edge["f"]] += 1
        for post in self.dataset.post_documents():
            posts[post["user_id"]][post["_id"]] = post["published_at"].timestamp()
        return followers, posts, follower_counts, following_counts

    async def load_redis(self) -> None:
        followers, posts, follower_counts, following_counts = self.views()
        counts = {
            kind: Counter(doc["post_id"] for doc in self.dataset.interaction_documents(kind, n))
            for kind, n in (
                ("comment", self.dataset.options.comments),
                ("reaction", self.dataset.options.reactions),
            )
        }
        for chunk in batched(self.dataset.post_documents(), self.dataset.options.batch_size):
            pipe = self.redis.pipeline(transaction=False)
            for post in chunk:
                pid, author = post["_id"], post["user_id"]
                pipe.set(f"publication:{pid}:state", "published")
                pipe.set(f"publication:{pid}:author", author)
                pipe.set(f"post_reactions:{pid}:count", counts["reaction"][pid])
                pipe.set(f"post_comments:{pid}:count", counts["comment"][pid])
                if followers[author]:
                    pipe.sadd(f"publication:{pid}:recipients", *followers[author])
            await pipe.execute()
        following: dict[str, list[str]] = defaultdict(list)
        for edge in self.dataset.relationships():
            if edge["status"] == "accepted":
                following[edge["f"]].append(edge["a"])
        for user in self.dataset.users:
            feed = {
                pid: score for author in following[user] for pid, score in posts[author].items()
            }
            pipe = self.redis.pipeline(transaction=False)
            if feed:
                pipe.zadd(f"feed:{user}", feed)
            pipe.set(f"followers:{user}:count", follower_counts[user])
            pipe.set(f"following:{user}:count", following_counts[user])
            await pipe.execute()
        for kind, n in (
            ("comment", self.dataset.options.comments),
            ("reaction", self.dataset.options.reactions),
        ):
            for chunk in batched(
                self.dataset.interaction_documents(kind, n), self.dataset.options.batch_size
            ):
                pipe = self.redis.pipeline(transaction=False)
                for doc in chunk:
                    # Historical notifications only; never broadcast old activity.
                    event = {
                        "event_id": str(
                            uuid5(self.dataset.namespace, f"notification:{doc['_id']}")
                        ),
                        "type": kind,
                        "post_id": doc["post_id"],
                        "actor_id": doc["user_id"],
                        "seed_dataset": self.dataset.name,
                    }
                    author = self.post_authors[doc["post_id"]]
                    pipe.hset(f"user:{author}:notifications", event["event_id"], json.dumps(event))
                await pipe.execute()
        messages: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for message in self.dataset.message_documents():
            messages[message["conversation_id"]].append(message)
        for group in self.dataset.group_documents():
            group_messages = messages[group["_id"]]
            pipe = self.redis.pipeline(transaction=False)
            for actor in group["participant_ids"]:
                unread = sum(
                    m["sender_id"] != actor and m["sequence"] > group["read_through"][actor]
                    for m in group_messages
                )
                pipe.set(f"conversation:{group['_id']}:unread:{actor}", unread)
            await pipe.execute()
        print(json.dumps({"phase": "redis", "status": "loaded"}), flush=True)

    @property
    def post_authors(self) -> dict[str, str]:
        if not hasattr(self, "_authors"):
            self._authors = {p["_id"]: p["user_id"] for p in self.dataset.post_documents()}
        return self._authors

    async def verify(self) -> dict[str, Any]:
        expected = {
            "users": self.dataset.options.users,
            "posts": self.dataset.options.posts,
            "comments": self.dataset.options.comments,
            "reactions": self.dataset.options.reactions,
            "messages": self.dataset.options.messages,
            "conversations": self.dataset.options.conversations,
            "moderation_reports": self.dataset.options.reports,
        }
        actual = {
            name: await self.db[name].count_documents({"seed_dataset": self.dataset.name})
            for name in expected
        }
        if actual != expected:
            raise RuntimeError(f"Cantidades inesperadas: {actual}; esperadas: {expected}")
        references = {
            "posts": [("user_id", "users")],
            "comments": [("user_id", "users"), ("post_id", "posts")],
            "reactions": [("user_id", "users"), ("post_id", "posts")],
            "messages": [("sender_id", "users"), ("conversation_id", "conversations")],
            "moderation_reports": [("reporter_id", "users"), ("post_id", "posts")],
            "conversations": [("participant_ids", "users")],
        }
        for collection, pairs in references.items():
            for field, target in pairs:
                pipeline: list[dict[str, Any]] = [{"$match": {"seed_dataset": self.dataset.name}}]
                if field == "participant_ids":
                    pipeline.append({"$unwind": "$participant_ids"})
                pipeline += [
                    {
                        "$lookup": {
                            "from": target,
                            "localField": field,
                            "foreignField": "_id",
                            "as": "target",
                        }
                    },
                    {"$match": {"target": {"$size": 0}}},
                    {"$limit": 1},
                ]
                if await (await self.db[collection].aggregate(pipeline)).to_list():
                    raise RuntimeError(f"Referencia inexistente: {collection}.{field}")
        async with self.graph.session() as session:
            result = await session.run(
                "MATCH (u:User {seed_dataset:$name}) RETURN collect(u.id) AS ids",
                name=self.dataset.name,
            )
            if set((await result.single(strict=True))["ids"]) != set(self.dataset.users):
                raise RuntimeError("UUID de usuarios diferentes entre MongoDB y Neo4j")
            result = await session.run(
                "MATCH (f:User)-[r]->(a:User) WHERE r.seed_dataset=$name "
                "RETURN f.id AS f, a.id AS a, type(r) AS kind, r.status AS status",
                name=self.dataset.name,
            )
            edges = [dict(row) async for row in result]
            if sorted(edges, key=str) != sorted(
                self.dataset.relationships() + self.dataset.blocks(), key=str
            ):
                raise RuntimeError("Relaciones Neo4j diferentes al dataset")
        counts: dict[str, dict[str, int]] = {}
        for collection in ("comments", "reactions"):
            result = await self.db[collection].aggregate(
                [
                    {"$match": {"post_id": {"$in": self.dataset.posts}}},
                    {"$group": {"_id": "$post_id", "n": {"$sum": 1}}},
                ]
            )
            counts[collection] = {doc["_id"]: doc["n"] async for doc in result}
        followers, posts, follower_counts, following_counts = self.views()
        for chunk in batched(self.dataset.posts, self.dataset.options.batch_size):
            pipe = self.redis.pipeline(transaction=False)
            for pid in chunk:
                pipe.mget(
                    f"post_reactions:{pid}:count",
                    f"post_comments:{pid}:count",
                    f"publication:{pid}:state",
                    f"publication:{pid}:author",
                )
                pipe.smembers(f"publication:{pid}:recipients")
            rows = await pipe.execute()
            for i, pid in enumerate(chunk):
                author = self.post_authors[pid]
                expected_row = [
                    str(counts["reactions"].get(pid, 0)).encode(),
                    str(counts["comments"].get(pid, 0)).encode(),
                    b"published",
                    author.encode(),
                ]
                if rows[i * 2] != expected_row or rows[i * 2 + 1] != {
                    u.encode() for u in followers[author]
                }:
                    raise RuntimeError(f"Contadores, marcador o destinatarios incorrectos: {pid}")
        following: dict[str, list[str]] = defaultdict(list)
        for edge in self.dataset.relationships():
            if edge["status"] == "accepted":
                following[edge["f"]].append(edge["a"])
        feed_references = 0
        for user in self.dataset.users:
            expected_feed = {
                pid.encode(): score
                for author in following[user]
                for pid, score in posts[author].items()
            }
            feed = dict(await self.redis.zrange(f"feed:{user}", 0, -1, withscores=True))
            if feed != expected_feed:
                raise RuntimeError(f"Feed inconsistente para {user}")
            row = await self.redis.mget(f"followers:{user}:count", f"following:{user}:count")
            if row != [str(follower_counts[user]).encode(), str(following_counts[user]).encode()]:
                raise RuntimeError(f"Contadores de seguimiento incorrectos: {user}")
            feed_references += len(feed)
        messages: dict[str, list[dict[str, Any]]] = defaultdict(list)
        async for message in self.db.messages.find({"seed_dataset": self.dataset.name}):
            messages[message["conversation_id"]].append(message)
        async for group in self.db.conversations.find({"seed_dataset": self.dataset.name}):
            history = messages[group["_id"]]
            if max((m["sequence"] for m in history), default=0) != group["sequence"]:
                raise RuntimeError(f"Secuencia de grupo inconsistente: {group['_id']}")
            for message in history:
                if message["sender_id"] not in group["participant_ids"]:
                    raise RuntimeError("Mensaje enviado por una persona fuera del grupo")
            for actor in group["participant_ids"]:
                unread = sum(
                    m["sender_id"] != actor and m["sequence"] > group["read_through"][actor]
                    for m in history
                )
                raw = await self.redis.get(f"conversation:{group['_id']}:unread:{actor}")
                if raw != str(unread).encode():
                    raise RuntimeError("Contador unread diferente al historial persistido")
        return {
            "counts": actual,
            "relationships": len(edges),
            "feed_references": feed_references,
            "cross_engine_ids": True,
            "references": True,
            "counters_and_feeds": True,
            "message_sequences_and_unread": True,
            "meets_requirement": actual["posts"] >= 50_000,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for key, default in SeedOptions().__dict__.items():
        parser.add_argument("--" + key.replace("_", "-"), type=int, default=default)
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--apply", action="store_true", help="Cargar el dataset (requiere SEED_PASSWORD)"
    )
    action.add_argument("--verify", action="store_true", help="Verificar la carga sin escribir")
    parser.add_argument(
        "--allow-small", action="store_true", help="Permitir carga reducida sólo para pruebas"
    )
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    options = SeedOptions(**{key: getattr(args, key) for key in SeedOptions().__dict__})
    dataset = Dataset(options)
    if not args.apply and not args.verify:
        print(json.dumps({"status": "plan_only", **dataset.summary()}, indent=2))
        return
    settings = get_settings()
    if settings.app_env not in ("development", "testing"):
        raise RuntimeError("La carga/verificación requiere development o testing")
    if args.apply and options.posts < 50_000 and not args.allow_small:
        raise ValueError("La entrega requiere 50000 publicaciones. Para pruebas usá --allow-small")
    store = DatasetStore(settings, dataset)
    started = time.perf_counter()
    try:
        result = (
            await store.verify()
            if args.verify
            else await store.load(os.environ.get("SEED_PASSWORD", ""))
        )
        print(
            json.dumps(
                {**result, "elapsed_seconds": round(time.perf_counter() - started, 3)}, indent=2
            )
        )
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(run())
