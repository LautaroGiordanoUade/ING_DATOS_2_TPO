"""Read-only index inventory, query plans and local timings on a loaded dataset."""

import argparse
import ast
import asyncio
import inspect
import json
import platform
import textwrap
import time
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from statistics import median
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoCommentRepository,
    MongoPostRepository,
)
from app.infrastructure.persistence.mongodb.repositories.messaging import MongoMessagingStore
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.personalized_feed import RedisPersonalizedFeed
from app.tools.dataset import Dataset, SeedOptions
from app.tools.seed_data import DatasetStore


def walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def summarize_plan(explanation: dict[str, Any]) -> dict[str, Any]:
    stats = explanation["executionStats"]
    winning = explanation["queryPlanner"]["winningPlan"]
    nodes = list(walk(winning))
    return {
        "indexes": sorted({n["indexName"] for n in nodes if "indexName" in n}),
        "stages": sorted({n["stage"] for n in nodes if "stage" in n}),
        "returned": stats["nReturned"],
        "documents_examined": stats["totalDocsExamined"],
        "keys_examined": stats["totalKeysExamined"],
        "server_ms": stats["executionTimeMillis"],
    }


def read_query(method: Callable[..., Any]) -> str:
    """Profile the literal Cypher used by the repository, avoiding a second copy."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            query = node.args[0].value
            if not query.strip().startswith(("MATCH", "UNWIND", "OPTIONAL MATCH")):
                raise ValueError("Only read queries may be profiled")
            return query
    raise ValueError("Repository no longer contains a literal read query")


async def timed(action: Callable[[], Awaitable[Any]], repeats: int) -> dict[str, Any]:
    await action()  # One warm-up, excluded from the measurements.
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        await action()
        samples.append(round((time.perf_counter() - started) * 1000, 3))
    return {"samples_ms": samples, "median_ms": median(samples)}


def queries(data: Dataset) -> list[dict[str, Any]]:
    user, other, post, group = data.users[0], data.users[1], data.posts[0], data.groups[0]
    visible = {
        "user_id": user,
        "publication_state": {"$ne": "pending"},
        "moderation_status": {"$ne": "hidden"},
        "visibility": "public",
    }
    pending = {"$in": ["pending", "running", "committing", "compensating"]}
    specs = [
        ("identity", "users", {"username": f"tpo{data.options.seed}_0000"}, {}, 1),
        ("P1_post", "posts", {"_id": post}, {}, 1),
        ("P2_recent", "posts", visible, {"published_at": -1, "_id": -1}, 20),
        (
            "P3_batch",
            "posts",
            {
                "_id": {"$in": data.posts[:20]},
                "publication_state": {"$ne": "pending"},
                "moderation_status": {"$ne": "hidden"},
                "visibility": "public",
            },
            {},
            20,
        ),
        (
            "P4_interests",
            "users",
            {"interests": {"$in": ["datos"]}, "account_status": {"$ne": "suspended"}},
            {"_id": 1},
            200,
        ),
        ("P5_reaction", "reactions", {"post_id": post, "user_id": other}, {}, 1),
        ("P5_comments_prefix", "comments", {"post_id": post}, {"created_at": -1, "_id": -1}, 21),
        (
            "P6_groups",
            "conversations",
            {"participant_ids": other, "archived": {"$ne": True}},
            {"_id": -1},
            21,
        ),
        (
            "P6_history",
            "messages",
            {"conversation_id": group, "sequence": {"$exists": True}},
            {"sequence": -1},
            21,
        ),
        (
            "P6_history_cursor",
            "messages",
            {"conversation_id": group, "sequence": {"$lt": 60}},
            {"sequence": -1},
            21,
        ),
        (
            "P6_pending_messages",
            "messages",
            {"conversation_id": group, "delivery_status": "pending"},
            {"sequence": 1},
            100,
        ),
        ("P7_reports_all", "moderation_reports", {}, {"reported_at": -1}, 100),
        (
            "P7_reports_pending",
            "moderation_reports",
            {"resolution_status": "pending"},
            {"reported_at": -1},
            100,
        ),
        ("P8_trace_posts", "posts", {"user_id": user}, {"published_at": -1}, 100),
        (
            "P8_trace_groups",
            "conversations",
            {"participant_ids": other, "archived": {"$ne": True}},
            {"created_at": -1},
            100,
        ),
        (
            "P1_queue",
            "publication_jobs",
            {"operation.status": {"$nin": ["completed", "compensated"]}},
            {"operation.created_at": 1},
            10,
        ),
        ("P2_queue", "follow_jobs", {"status": pending}, {"created_at": 1}, 10),
        ("P7_queue", "moderation_jobs", {"status": pending}, {"created_at": 1}, 10),
        ("P8_queue", "account_jobs", {"status": pending}, {"created_at": 1}, 10),
        ("P7_publication_lookup", "publication_jobs", {"post.id": post}, {}, 1),
    ]
    return [
        dict(name=n, collection=c, filter=f, sort=s, limit=limit) for n, c, f, s, limit in specs
    ]


async def audit(data: Dataset, repeats: int) -> dict[str, Any]:
    store = DatasetStore(get_settings(), data)
    try:
        manifest = await store.db.seed_datasets.find_one({"_id": data.name})
        if not manifest or manifest.get("status") != "completed":
            raise ValueError("Load and verify the dataset before auditing")
        if manifest["config"] != data.config():
            raise ValueError("This command requires the default dataset configuration")
        inventory = {}
        for name in sorted(await store.db.list_collection_names()):
            stats = await store.db.command("collStats", name)
            inventory[name] = {
                "count": stats["count"],
                "data_bytes": stats["size"],
                "index_bytes": stats["totalIndexSize"],
                "indexes": await store.db[name].index_information(),
            }
        mongo = []
        for spec in queries(data):
            command = {
                "find": spec["collection"],
                **{k: v for k, v in spec.items() if k not in ("name", "collection")},
            }
            if not command["sort"]:
                command.pop("sort")
            plan = await store.db.command("explain", command, verbosity="executionStats")

            async def fetch(cmd: dict[str, Any] = command) -> Any:
                # The bound is <=200; exhaust the cursor so timing includes every batch.
                cursor = store.db[cmd["find"]].find(cmd["filter"])
                if "sort" in cmd:
                    cursor = cursor.sort(list(cmd["sort"].items()))
                return await cursor.limit(cmd["limit"]).to_list()

            row = {**spec, **summarize_plan(plan), **await timed(fetch, repeats)}
            if spec["name"] in ("P2_recent", "P6_history", "P8_trace_posts"):
                natural = await store.db.command(
                    "explain",
                    {**command, "hint": {"$natural": 1}},
                    verbosity="executionStats",
                )
                row["collection_scan_comparison"] = summarize_plan(natural)
            mongo.append(row)
        graph_repo = Neo4jSocialGraphRepository(store.graph)
        graph_queries: list[tuple[str, Callable[..., Any], dict[str, Any]]] = [
            ("P1_followers", graph_repo.follower_ids, {"user_id": data.users[0]}),
            (
                "P4_mutual",
                graph_repo.get_mutual_friends,
                {"u1": data.users[1], "u2": data.users[6]},
            ),
            (
                "P4_candidates",
                graph_repo.suggestion_candidates,
                {"id": data.users[1], "after": None, "limit": 200},
            ),
            ("P8_relationships", graph_repo.trace_relationships, {"id": data.users[0]}),
        ]
        graph = []
        async with store.graph.session(default_access_mode="READ") as session:
            constraints = [r.data() async for r in await session.run("SHOW CONSTRAINTS")]
            indexes = [r.data() async for r in await session.run("SHOW INDEXES")]
            for name, method, parameters in graph_queries:
                query = read_query(method)

                async def run(q: str = query, p: dict[str, Any] = parameters) -> Any:
                    result = await session.run(q, p)
                    return await result.data()

                timing = await timed(run, repeats)
                result = await session.run("PROFILE " + query, parameters)
                await result.data()
                summary = await result.consume()
                nodes = list(walk(summary.profile))
                graph.append(
                    {
                        "name": name,
                        "query": query,
                        "parameters": parameters,
                        **timing,
                        "operators": sorted(
                            {n["operatorType"] for n in nodes if "operatorType" in n}
                        ),
                        "db_hits": sum(n.get("dbHits", 0) for n in nodes),
                    }
                )
        feed = RedisPersonalizedFeed(store.redis)
        reader = UUID(data.users[1])
        posts = MongoPostRepository(store.db)
        comments = MongoCommentRepository(store.db)
        messaging = MongoMessagingStore(store.db)
        reads = [
            ("P3_redis_candidates", lambda: feed.candidates(reader, 4e9, "~")),
            ("P3_mongo_batch", lambda: posts.get_many(tuple(map(UUID, data.posts[:20])))),
            ("P5_visible_comments", lambda: comments.visible_page(UUID(data.posts[0]), None, 21)),
            ("P6_history_with_authors", lambda: messaging.history(UUID(data.groups[0]), None, 20)),
        ]
        repository_timings = [
            {"name": name, **await timed(action, repeats)} for name, action in reads
        ]
        mongo_info = await store.mongo.server_info()
        redis_info = await store.redis.info("server")
        return {
            "recorded_at": datetime.now(UTC).isoformat(),
            "dataset": data.name,
            "manifest_checksum": manifest["sha256"],
            "conditions": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "mongo_version": mongo_info["version"],
                "redis_version": redis_info["redis_version"],
                "repeats": repeats,
                "warmup": 1,
                "scope": "read-only, sequential, warm local queries; no HTTP or write latency",
            },
            "mongodb": {"inventory": inventory, "queries": mongo},
            "neo4j": {"constraints": constraints, "indexes": indexes, "queries": graph},
            "redis": {
                "keys": await store.redis.dbsize(),
                "reader_feed_members": await store.redis.zcard(f"feed:{reader}"),
            },
            "repository_timings": repository_timings,
        }
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--repeats", type=int, choices=range(1, 16), default=5)
    args = parser.parse_args()
    result = asyncio.run(audit(Dataset(SeedOptions(seed=args.seed)), args.repeats))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
