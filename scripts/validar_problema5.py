"""Live Docker checks. Creates isolated data and leaves it for inspection."""

import asyncio
import json
import urllib.error
import urllib.request
from uuid import uuid4

from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from app.core.config import get_settings
from app.domain.entities import Post
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.mappers.post_mapper import post_to_document

results = []


def check(name, ok, detail):
    results.append({"test": name, "ok": bool(ok), "detail": detail})
    print(json.dumps(results[-1], ensure_ascii=True), flush=True)


def request(method, route, payload, headers=None):
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/problems/5/" + route,
        data=json.dumps(payload).encode(),
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            raw = json.loads(raw)
        except ValueError:
            pass
        return e.code, raw


async def main():
    s = get_settings()
    mongo = AsyncMongoClient(s.mongodb_url)
    db = mongo[s.mongodb_database]
    redis = Redis.from_url(s.redis_url)
    author, actor, post = str(uuid4()), str(uuid4()), str(uuid4())
    from uuid import UUID

    await db.posts.insert_one(
        post_to_document(
            Post(
                id=UUID(post),
                user_id=UUID(author),
                text="Validacion aislada P5",
                moderation_status=ModerationStatus.APPROVED,
            )
        )
    )
    payload = {"post_id": post, "user_id": actor, "kind": "like"}

    async def call(method, route, body, headers=None):
        return await asyncio.to_thread(request, method, route, body, headers)

    async def counter(kind):
        return int(await redis.get(f"post_{kind}:{post}:count") or 0)

    async def reaction_state():
        docs = await db.reactions.find({"post_id": post}).to_list()
        return len(docs), await counter("reactions"), [d["kind"] for d in docs]

    async def comment_state():
        return await db.comments.count_documents({"post_id": post}), await counter("comments")

    code, body = await call("POST", "reaction", payload)
    state = await reaction_state()
    check(
        "Crear reaccion", code == 202 and state == (1, 1, ["like"]), {"http": code, "state": state}
    )
    check(
        "Notificacion al autor",
        await redis.hlen(f"user:{author}:notifications") == 1,
        {"notifications": await redis.hlen(f"user:{author}:notifications")},
    )
    await call("POST", "reaction", payload)
    state = await reaction_state()
    check("Repetir reaccion", state == (1, 1, ["like"]), state)
    await call("POST", "reaction", {**payload, "kind": "love"})
    state = await reaction_state()
    check("Cambiar reaccion", state == (1, 1, ["love"]), state)
    removal = {"post_id": post, "user_id": actor}
    await call("DELETE", "reaction", removal)
    state = await reaction_state()
    check("Borrar reaccion", state[:2] == (0, 0), state)
    await call("DELETE", "reaction", removal)
    state = await reaction_state()
    check("Repetir borrado", state[:2] == (0, 0), state)
    for step in [
        "mongo_upsert_reaction",
        "redis_increment_reaction_counter",
        "redis_publish_notification",
    ]:
        code, body = await call("POST", "reaction", payload, {"X-Fail-At-Step": step})
        state = await reaction_state()
        check(
            "Compensacion reaccion " + step,
            code == 500 and state[:2] == (0, 0),
            {"http": code, "state": state},
        )
    comment = {"post_id": post, "user_id": actor, "text": "Comentario de validacion"}
    idem = "validar-" + str(uuid4())
    code, first = await call("POST", "comment", comment, {"Idempotency-Key": idem})
    code2, second = await call("POST", "comment", comment, {"Idempotency-Key": idem})
    state = await comment_state()
    check(
        "Comentario e idempotencia",
        code == code2 == 202 and first == second and state == (1, 1),
        {"state": state, "same_response": first == second},
    )
    notifications = await redis.hgetall(f"user:{author}:notifications")
    check(
        "Notificacion comentario",
        any(json.loads(v)["type"] == "comment" for v in notifications.values()),
        {"notifications": len(notifications)},
    )
    for step in [
        "mongo_create_comment",
        "redis_increment_comment_counter",
        "redis_publish_notification",
    ]:
        key = "validar-" + str(uuid4())
        code, body = await call(
            "POST", "comment", comment, {"Idempotency-Key": key, "X-Fail-At-Step": step}
        )
        state = await comment_state()
        check(
            "Compensacion comentario " + step,
            code == 500 and state == (1, 1),
            {"http": code, "state": state},
        )
    responses = await asyncio.gather(*[call("POST", "reaction", payload) for _ in range(20)])
    state = await reaction_state()
    check(
        "20 reacciones concurrentes mismo usuario",
        all(c == 202 for c, b in responses) and state[:2] == (1, 1),
        {"codes": [c for c, b in responses], "state": state},
    )
    responses = await asyncio.gather(*[call("DELETE", "reaction", removal) for _ in range(20)])
    state = await reaction_state()
    check(
        "20 borrados concurrentes",
        all(c == 200 for c, b in responses) and state[:2] == (0, 0),
        {"codes": [c for c, b in responses], "state": state},
    )
    key = "validar-" + str(uuid4())
    responses = await asyncio.gather(
        *[call("POST", "comment", comment, {"Idempotency-Key": key}) for _ in range(20)]
    )
    state = await comment_state()
    check(
        "20 comentarios concurrentes misma clave",
        all(c in (202, 409) for c, b in responses) and state == (2, 2),
        {"codes": [c for c, b in responses], "state": state},
    )
    # Repeat create/delete overlap: clamp-to-zero counters can lose a decrement.
    bad = []
    for i in range(30):
        await call("DELETE", "reaction", removal)
        await asyncio.gather(call("POST", "reaction", payload), call("DELETE", "reaction", removal))
        state = await reaction_state()
        if state[0] != state[1]:
            bad.append({"round": i, "state": state})
            break
    check("Crear y borrar simultaneamente", not bad, bad or "30 rondas consistentes")
    print(
        "TEST_DATA " + json.dumps({"post_id": post, "author_id": author, "actor_id": actor}),
        flush=True,
    )
    print(
        "SUMMARY " + json.dumps({"passed": sum(r["ok"] for r in results), "total": len(results)}),
        flush=True,
    )
    await mongo.close()
    await redis.aclose()


asyncio.run(main())
