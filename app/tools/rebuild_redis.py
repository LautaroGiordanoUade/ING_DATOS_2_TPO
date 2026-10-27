"""Offline logical recovery into an empty Redis database; never flushes existing data."""

import argparse
import asyncio
import hashlib
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

from app.core.config import get_settings
from app.tools.dataset import Dataset, SeedOptions
from app.tools.seed_data import DatasetStore

MARKER = "maintenance:redis-rebuild:v1"
TERMINAL = ["completed", "compensated"]
_CLAIM = """
if redis.call('DBSIZE') ~= 0 then return 0 end
redis.call('SET', KEYS[1], ARGV[1])
return 1
"""


@contextmanager
def rebuild_lock() -> Iterator[None]:
    import fcntl

    directory = Path(os.environ.get("INTERACTION_LOCK_DIR", "/home/appuser/interaction-locks"))
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "redis-rebuild.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Otra reconstrucción está ejecutándose") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class RecoverySources:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.posts: dict[str, dict[str, Any]] = {}
        self.gates: dict[tuple[str, str], str] = {}
        self.accepted: set[tuple[str, str]] = set()
        self.blocks: set[frozenset[str]] = set()
        self.reactions: Counter[str] = Counter()
        self.comments: Counter[str] = Counter()
        self.unread: dict[str, dict[str, int]] = {}
        self.notified: dict[str, int] = {}
        self.aborted: set[str] = set()

    @classmethod
    async def load(cls, store: DatasetStore) -> "RecoverySources":
        result = cls()
        for collection, status in (
            ("publication_jobs", "operation.status"),
            ("follow_jobs", "status"),
            ("moderation_jobs", "status"),
            ("account_jobs", "status"),
            ("operations", "status"),
        ):
            if await store.db[collection].find_one({status: {"$nin": TERMINAL}}, {"_id": 1}):
                raise ValueError(f"{collection}: hay operaciones no terminales; recuperar respaldo")
        if await store.db.posts.find_one({"publication_state": "pending"}, {"_id": 1}):
            raise ValueError("Hay publicaciones pendientes; recuperar respaldo")
        if await store.db.messages.find_one({"delivery_status": "pending"}, {"_id": 1}):
            raise ValueError("Hay mensajes pendientes; recuperar respaldo")
        if await store.db.conversations.find_one({"redis_pending": True}, {"_id": 1}):
            raise ValueError("Hay sincronizaciones de lectura pendientes; recuperar respaldo")
        if await store.db.seed_datasets.find_one({"status": {"$ne": "completed"}}, {"_id": 1}):
            raise ValueError("Hay cargas de datos incompletas; recuperar respaldo")
        result.users = {
            str(d["_id"]): d async for d in store.db.users.find({}, {"account_status": 1})
        }
        result.posts = {
            str(d["_id"]): d
            async for d in store.db.posts.find(
                {},
                {
                    "user_id": 1,
                    "published_at": 1,
                    "visibility": 1,
                    "publication_state": 1,
                    "moderation_status": 1,
                },
            )
        }
        for post in result.posts.values():
            if post["user_id"] not in result.users:
                raise ValueError("Publicación con autor ausente en MongoDB")
            if not isinstance(post.get("published_at"), datetime):
                raise ValueError("Publicación sin fecha válida")
        # Seed negative gates from old snapshots, before overlaying today's graph.
        # Otherwise P7/P8 could resurrect an author who was unfollowed before the loss.
        for collection in ("moderation_jobs", "account_post_snapshots"):
            async for doc in store.db[collection].find({}, {"post_id": 1, "snapshot.feeds": 1}):
                snapshot_post = result.posts.get(str(doc.get("post_id")))
                if snapshot_post:
                    for feed in (doc.get("snapshot") or {}).get("feeds", {}):
                        if feed.startswith("feed:"):
                            result.gates[(feed[5:], snapshot_post["user_id"])] = "none"
        async for doc in store.db.publication_jobs.find(
            {},
            {
                "post.id": 1,
                "post.user_id": 1,
                "followers": 1,
                "operation.status": 1,
            },
        ):
            post = doc.get("post", {})
            if doc.get("operation", {}).get("status") == "compensated":
                if post.get("id") not in result.posts:
                    result.aborted.add(post["id"])
            for recipient in doc.get("followers") or []:
                result.gates[(recipient, post["user_id"])] = "none"
        async for doc in store.db.follow_jobs.find({}, {"follower_id": 1, "followed_id": 1}):
            result.gates[(doc["follower_id"], doc["followed_id"])] = "none"
        async with store.graph.session(default_access_mode="READ") as session:
            edges = await session.run(
                "MATCH (f:User)-[r:FOLLOWS|BLOCKS]->(a:User) "
                "RETURN f.id AS f, a.id AS a, type(r) AS kind, "
                "coalesce(r.status,'accepted') AS status"
            )
            seen: set[tuple[str, str]] = set()
            async for edge in edges:
                pair = (str(edge["f"]), str(edge["a"]))
                if not all(identifier in result.users for identifier in pair):
                    continue  # Missing Mongo accounts can never receive or author a feed.
                if edge["kind"] == "BLOCKS":
                    result.blocks.add(frozenset(pair))
                else:
                    if pair in seen:
                        raise ValueError(
                            "FOLLOWS duplicados; reconciliar el grafo antes de recuperar"
                        )
                    seen.add(pair)
                    result.gates[pair] = str(edge["status"])
                    if edge["status"] == "accepted":
                        result.accepted.add(pair)
        for pair in list(result.gates):
            if frozenset(pair) in result.blocks:
                result.gates[pair] = "none"
        for collection, target in (("reactions", result.reactions), ("comments", result.comments)):
            cursor = await store.db[collection].aggregate(
                [
                    {"$group": {"_id": "$post_id", "count": {"$sum": 1}}},
                ]
            )
            async for row in cursor:
                target[str(row["_id"])] = int(row["count"])
        messages: dict[str, list[dict[str, Any]]] = defaultdict(list)
        async for doc in store.db.messages.find(
            {"sequence": {"$type": "number"}},
            {"conversation_id": 1, "sender_id": 1, "sequence": 1},
        ):
            messages[str(doc["conversation_id"])].append(doc)
        async for group in store.db.conversations.find(
            {}, {"participant_ids": 1, "read_through": 1}
        ):
            identifier = str(group["_id"])
            history = messages[identifier]
            result.notified[identifier] = max((m["sequence"] for m in history), default=0)
            result.unread[identifier] = {
                actor: sum(
                    m["sender_id"] != actor
                    and m["sequence"] > group.get("read_through", {}).get(actor, 0)
                    for m in history
                )
                for actor in group["participant_ids"]
            }
        return result

    def commands(self) -> Iterator[tuple[Any, ...]]:
        suspended = {u for u, doc in self.users.items() if doc.get("account_status") == "suspended"}
        followers: dict[str, list[str]] = defaultdict(list)
        counts_in: Counter[str] = Counter()
        counts_out: Counter[str] = Counter()
        for recipient, author in sorted(self.accepted):
            counts_in[author] += 1
            counts_out[recipient] += 1
            if recipient != author and frozenset((recipient, author)) not in self.blocks:
                followers[author].append(recipient)
        for user in sorted(self.users):
            yield "SET", f"followers:{user}:count", counts_in[user]
            yield "SET", f"following:{user}:count", counts_out[user]
            if user in suspended:
                yield "SET", f"account:{user}:suspended", "suspended"
        for (recipient, author), status in sorted(self.gates.items()):
            yield "SET", f"follow:{recipient}:{author}:state", status
        for pid in sorted(self.aborted):
            yield "SET", f"publication:{pid}:state", "aborted"
        for pid, post in sorted(self.posts.items()):
            author = post["user_id"]
            hidden = post.get("moderation_status") == "hidden"
            blocked = author in suspended
            yield "SET", f"publication:{pid}:author", author
            yield "SET", f"publication:{pid}:state", "published"
            if hidden:
                yield "SET", f"moderation:{pid}:hidden", "hidden"
            if blocked:
                yield "SET", f"suspension:{pid}:hidden", "hidden"
            for namespace, count in (
                ("post_reactions", self.reactions[pid]),
                ("post_comments", self.comments[pid]),
            ):
                key = f"{namespace}:{pid}:count"
                yield "SET", key, 0 if hidden or blocked else count
                if hidden or blocked:
                    yield "SET", key + ":moderation_saved", count
            if post.get("visibility", "public") != "public":
                continue
            timestamp = post["published_at"]
            score = (
                timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp
            ).timestamp()
            for recipient in followers[author]:
                yield "SADD", f"publication:{pid}:recipients", recipient
                if hidden:
                    continue
                if blocked:
                    yield "HSET", f"account:{author}:deferred_out", f"{pid}|{recipient}", score
                if recipient in suspended:
                    yield "HSET", f"account:{recipient}:deferred_in", pid, score
                if not blocked and recipient not in suspended:
                    yield "ZADD", f"feed:{recipient}", score, pid
        for group, participants in sorted(self.unread.items()):
            for actor, count in sorted(participants.items()):
                yield "SET", f"conversation:{group}:unread:{actor}", count
                yield "SET", f"conversation:{group}:notified:{actor}", self.notified[group]

    def plan(self) -> dict[str, Any]:
        digest = hashlib.sha256()
        count = 0
        feed_counts: Counter[str] = Counter()
        for command in self.commands():
            digest.update(json.dumps(command, separators=(",", ":")).encode() + b"\n")
            count += 1
            if command[0] == "ZADD":
                feed_counts[command[1]] += 1
        if max(feed_counts.values(), default=0) > 100_000:
            raise ValueError("Un feed superaría 100000 referencias; requiere otra estrategia")
        return {
            "fingerprint": digest.hexdigest(),
            "commands": count,
            "users": len(self.users),
            "posts": len(self.posts),
            "accepted_follows": len(self.accepted),
            "feed_references": sum(feed_counts.values()),
            "conversations": len(self.unread),
            "not_recovered": [
                "notifications",
                "pubsub_events",
                "presence",
                "feed_cursors",
                "redis_only_idempotency",
                "exact_historical_feed_membership",
            ],
        }


async def verify_commands(store: DatasetStore, sources: RecoverySources) -> int:
    checked = 0
    for chunk in batched(sources.commands(), 500):
        pipe = store.redis.pipeline(transaction=False)
        for command in chunk:
            kind, key, *args = command
            if kind == "SET":
                pipe.get(key)
            elif kind == "ZADD":
                pipe.zscore(key, args[1])
            elif kind == "SADD":
                pipe.sismember(key, args[0])
            elif kind == "HSET":
                pipe.hget(key, args[0])
        values = await pipe.execute()
        for command, value in zip(chunk, values, strict=True):
            kind, key, *args = command
            if kind == "SET":
                valid = value == str(args[0]).encode()
            elif kind == "SADD":
                valid = bool(value)
            else:
                expected = args[0] if kind == "ZADD" else args[1]
                valid = value is not None and float(value) == float(expected)
            if not valid:
                raise ValueError(f"Vista reconstruida diferente a la fuente: {key}")
            checked += 1
    return checked


async def recover(
    store: DatasetStore,
    *,
    apply: bool = False,
    offline: bool = False,
    resume: bool = False,
    verify: bool = False,
) -> dict[str, Any]:
    if (apply or verify) and not offline:
        raise ValueError(
            "Detener frontend/API/workers y confirmar --offline antes de --apply/--verify"
        )
    sources = await RecoverySources.load(store)
    plan = sources.plan()
    keys = await store.redis.dbsize()
    if verify:
        with rebuild_lock():
            raw = await store.redis.get(MARKER)
            marker = json.loads(raw) if raw else {}
            if (
                marker.get("fingerprint") != plan["fingerprint"]
                or marker.get("status") != "completed"
            ):
                raise ValueError("No hay una reconstrucción completa con las mismas fuentes")
            checked = await verify_commands(store, sources)
            return {**plan, "status": "verified", "verified_commands": checked, "target_keys": keys}
    if not apply:
        return {**plan, "status": "plan", "target_keys": keys, "requires_empty_target": True}
    with rebuild_lock():
        raw = await store.redis.get(MARKER)
        if resume:
            marker = json.loads(raw) if raw else {}
            if (
                marker.get("fingerprint") != plan["fingerprint"]
                or marker.get("status") != "running"
            ):
                raise ValueError("No hay una recuperación interrumpida con las mismas fuentes")
        else:
            marker = {
                "fingerprint": plan["fingerprint"],
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
            }
            claimed = await store.redis.eval(_CLAIM, 1, MARKER, json.dumps(marker))
            if not claimed:
                raise ValueError(
                    "Redis no está vacío; no se modifica. Usar otro destino o un respaldo"
                )
        started = time.perf_counter()
        for chunk in batched(sources.commands(), 500):
            pipe = store.redis.pipeline(transaction=False)
            for command in chunk:
                pipe.execute_command(*command)
            await pipe.execute()
        checked = await verify_commands(store, sources)
        marker["status"] = "completed"
        marker["completed_at"] = datetime.now(UTC).isoformat()
        await store.redis.set(MARKER, json.dumps(marker))
        return {
            **plan,
            "status": "completed",
            "target_keys": await store.redis.dbsize(),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "verified_commands": checked,
        }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    # DatasetStore supplies clients only; no dataset loading or mutation is invoked.
    store = DatasetStore(get_settings(), Dataset(SeedOptions()))
    try:
        return await recover(
            store, apply=args.apply, offline=args.offline, resume=args.resume, verify=args.verify
        )
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.resume and not args.apply:
        parser.error("--resume requiere --apply --offline")
    if args.verify and args.apply:
        parser.error("--verify no se combina con --apply")
    print(json.dumps(asyncio.run(run(args)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
