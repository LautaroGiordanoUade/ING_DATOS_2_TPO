"""Smoke HTTP con usuarios nuevos. Requiere Compose/API/workers iniciados."""

import json
import os
import secrets
import time
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4

BASE = os.getenv("P2_BASE_URL", "http://127.0.0.1:8000")


def request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    key: str | None = None,
    fail: str | None = None,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if key:
        headers["Idempotency-Key"] = key
    if fail:
        headers["X-Fail-At-Step"] = fail
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers=headers,
        data=None if payload is None else json.dumps(payload).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()
            return response.status, json.loads(data) if data else None
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def wait(job: dict[str, Any], token: str, publication: bool = False) -> dict[str, Any]:
    prefix = "/api/v1/problems" if publication else "/api/v1/social"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        code, result = request("GET", f"{prefix}/operations/{job['operation_id']}", token=token)
        assert code == 200, result
        if result["status"] in ("completed", "compensated", "failed"):
            return dict(result)
        time.sleep(0.2)
    raise AssertionError("El worker no termino en 30 segundos")


def main() -> None:
    suffix, password = uuid4().hex[:12], secrets.token_urlsafe(24)
    accounts: dict[str, tuple[str, str]] = {}
    for role in ("reader", "public", "private"):
        username = f"qa-p2-{suffix}-{role}"
        code, user = request(
            "POST",
            "/api/v1/users",
            {
                "username": username,
                "full_name": f"QA P2 {role}",
                "email": username + "@qa.invalid",
                "password": password,
                "account_type": "private" if role == "private" else "public",
            },
        )
        assert code == 201, user
        code, auth = request(
            "POST",
            "/api/v1/users/login",
            {
                "username": username,
                "password": password,
            },
        )
        assert code == 200, auth
        accounts[role] = (user["id"], auth["access_token"])
    reader, token = accounts["reader"]
    posts: dict[str, str] = {}
    for role in ("public", "private"):
        author, auth = accounts[role]
        code, job = request(
            "POST",
            "/api/v1/problems/1/publish",
            {
                "user_id": author,
                "text": f"Smoke P2 {suffix} {role}",
                "interests": ["data"],
            },
            token=auth,
        )
        assert code == 202, job
        assert wait(job, auth, publication=True)["status"] == "completed"
        posts[role] = job["post_id"]

    def visible() -> list[str]:
        code, result = request("GET", f"/api/v1/problems/1/feed-preview/{reader}")
        assert code == 200, result
        return list(result["post_ids"])

    def command(role: str, method: str = "POST", fail: str | None = None) -> dict[str, Any]:
        author = accounts[role][0]
        key = str(uuid4())
        payload = {"user_id": reader, "followed_user_id": author}
        code, job = request(method, "/api/v1/social/follows", payload, token, key, fail)
        assert code == 202, job
        replay_code, replay = request(method, "/api/v1/social/follows", payload, token, key, fail)
        assert replay_code == 202 and replay["operation_id"] == job["operation_id"], replay
        return wait(job, token)

    assert command("public")["desired"] == "accepted"
    assert posts["public"] in visible()
    assert command("private")["desired"] == "pending"
    assert posts["private"] not in visible()
    author, owner_token = accounts["private"]
    payload = {"user_id": reader, "followed_user_id": author}
    assert request("POST", "/api/v1/social/follows/approve", payload, token)[0] == 403
    code, job = request("POST", "/api/v1/social/follows/approve", payload, owner_token)
    assert code == 202, job
    assert wait(job, owner_token)["status"] == "completed"
    assert posts["private"] in visible()
    assert command("public", "DELETE", "redis_follow_counters")["status"] == "compensated"
    assert posts["public"] in visible()
    assert command("public", "DELETE")["status"] == "completed"
    assert posts["public"] not in visible() and posts["private"] in visible()
    assert command("private", "DELETE")["status"] == "completed"
    counts = request("GET", f"/api/v1/social/counts/{reader}", token=token)[1]
    assert counts["following"] == 0, counts
    print(
        json.dumps(
            {
                "result": "OK",
                "users": {name: user[0] for name, user in accounts.items()},
                "checks": [
                    "registro/login",
                    "publico",
                    "privado/aprobacion",
                    "idempotencia",
                    "compensacion",
                    "unfollow/feed",
                    "contadores",
                ],
                "note": "Datos QA nuevos conservados; no modifica usuarios existentes.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
