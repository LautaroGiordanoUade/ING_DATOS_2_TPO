"""Run inside the API container; creates isolated users, posts and graph edges."""

import asyncio
import json
import time
import urllib.error
import urllib.request
from uuid import uuid4

from neo4j import AsyncGraphDatabase
from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from app.core.config import get_settings


def request(method, path, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/problems/" + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


async def wait_operation(operation_id):
    for _ in range(600):
        code, operation = await asyncio.to_thread(request, "GET", f"operations/{operation_id}")
        if code == 200 and operation["status"] in ("completed", "compensated"):
            return operation
        await asyncio.sleep(0.05)
    raise AssertionError(f"Operation timed out: {operation_id}")


async def main():
    settings = get_settings()
    mongo = AsyncMongoClient(settings.mongodb_url)
    db = mongo[settings.mongodb_database]
    redis = Redis.from_url(settings.redis_url)
    graph = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    author = str(uuid4())
    audience = [str(uuid4()) for _ in range(2000)]
    excluded = [str(uuid4()) for _ in range(3)]
    async with graph.session() as session:
        await session.run("CREATE (:User {id: $id, account_status: 'active'})", id=author)
        result = await session.run(
            "UNWIND $ids AS id MATCH (a:User {id: $author}) "
            "CREATE (u:User {id:id, account_status:'active'})-[:FOLLOWS {status:'accepted'}]->(a)",
            ids=audience,
            author=author,
        )
        await result.consume()
        result = await session.run(
            "MATCH (a:User {id:$author}) "
            "CREATE (:User {id:$pending})-[:FOLLOWS {status:'pending'}]->(a) "
            "CREATE (:User {id:$suspended, account_status:'suspended'})-[:FOLLOWS]->(a) "
            "CREATE (b:User {id:$blocked})-[:FOLLOWS]->(a) CREATE (a)-[:BLOCKS]->(b)",
            author=author,
            pending=excluded[0],
            suspended=excluded[1],
            blocked=excluded[2],
        )
        await result.consume()
    await db.users.insert_many(
        [
            {"_id": user, "username": "qa-p1-" + user, "account_status": "active"}
            for user in [author, *audience, *excluded]
        ]
    )
    payload = {"user_id": author, "text": "Publicacion P1 QA", "interests": ["datos", "python"]}
    key = "qa-p1-" + str(uuid4())
    start = time.perf_counter()
    code, accepted = await asyncio.to_thread(
        request, "POST", "1/publish", payload, {"Idempotency-Key": key}
    )
    latency = time.perf_counter() - start
    assert code == 202, accepted
    operation = await wait_operation(accepted["operation_id"])
    assert operation["status"] == "completed", operation
    post_id = accepted["post_id"]
    doc = await db.posts.find_one({"_id": post_id})
    assert doc["interests"] == ["datos", "python"] and doc["publication_state"] == "published"
    pipe = redis.pipeline(transaction=False)
    for user in audience + excluded:
        pipe.zscore(f"feed:{user}", post_id)
    scores = await pipe.execute()
    assert all(score is not None for score in scores[:2000])
    assert all(score is None for score in scores[2000:])
    code, preview = await asyncio.to_thread(request, "GET", "1/feed-preview/" + audience[0])
    assert code == 200 and post_id in preview["post_ids"]
    print(
        f"PASS: 2000 followers, interests, audience filters, visibility; API {latency:.3f}s",
        flush=True,
    )
    responses = await asyncio.gather(
        *[
            asyncio.to_thread(request, "POST", "1/publish", payload, {"Idempotency-Key": key})
            for _ in range(20)
        ]
    )
    assert all(c == 202 and body["post_id"] == post_id for c, body in responses)
    assert await db.publication_jobs.count_documents({"post.user_id": author}) == 1
    code, body = await asyncio.to_thread(
        request, "POST", "1/publish", {**payload, "text": "otro texto"}, {"Idempotency-Key": key}
    )
    assert code == 409, body
    print("PASS: concurrent replay returns one post; changed payload returns 409", flush=True)
    for step in (
        "mongo_create_post",
        "neo4j_load_followers",
        "redis_feed_update",
        "redis_feed_partial",
        "publication_commit",
    ):
        code, failed = await asyncio.to_thread(
            request,
            "POST",
            "1/publish",
            payload,
            {"Idempotency-Key": str(uuid4()), "X-Fail-At-Step": step},
        )
        assert code == 202, failed
        operation = await wait_operation(failed["operation_id"])
        assert operation["status"] == "compensated", operation
        assert await db.posts.find_one({"_id": failed["post_id"]}) is None
        pipe = redis.pipeline(transaction=False)
        for user in audience:
            pipe.zscore(f"feed:{user}", failed["post_id"])
        assert all(score is None for score in await pipe.execute())
        assert await redis.zscore(f"feed:{audience[0]}", post_id) is not None
        print("PASS: rollback " + step + "; no residual post or feed entries", flush=True)
    code, body = await asyncio.to_thread(request, "POST", "1/publish", {**payload, "interests": []})
    assert code == 422, body
    print("PASS: interests required", flush=True)
    print(json.dumps({"author": author, "first_follower": audience[0], **accepted}), flush=True)
    await graph.close()
    await mongo.close()
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
