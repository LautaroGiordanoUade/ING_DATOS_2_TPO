"""Smoke HTTP P3: creates two QA users and 46 real P1 publications; no resets."""

import concurrent.futures
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from uuid import uuid4

BASE = os.getenv("P3_BASE_URL", "http://127.0.0.1:8000")


def request(
    method: str, path: str, payload: dict[str, Any] | None = None, token: str | None = None
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers=headers,
        data=None if payload is None else json.dumps(payload).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def wait(job: dict[str, Any], token: str, publication: bool = False) -> dict[str, Any]:
    prefix = "problems" if publication else "social"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        code, result = request(
            "GET", f"/api/v1/{prefix}/operations/{job['operation_id']}", token=token
        )
        assert code == 200, result
        if result["status"] in ("completed", "compensated", "failed"):
            assert result["status"] == "completed", result
            return dict(result)
        time.sleep(0.2)
    raise AssertionError("Worker did not finish in 30 seconds")


def main() -> None:
    suffix, password = uuid4().hex[:12], secrets.token_urlsafe(24)
    users: list[tuple[str, str]] = []
    for role in ("reader", "author"):
        username = f"qa-p3-{suffix}-{role}"
        code, user = request(
            "POST",
            "/api/v1/users",
            {
                "username": username,
                "full_name": f"P3 {role}",
                "email": username + "@qa.invalid",
                "password": password,
            },
        )
        assert code == 201, user
        code, auth = request(
            "POST", "/api/v1/users/login", {"username": username, "password": password}
        )
        assert code == 200, auth
        users.append((user["id"], auth["access_token"]))
    (reader, token), (author, author_token) = users
    payload = {"user_id": reader, "followed_user_id": author}
    code, job = request("POST", "/api/v1/social/follows", payload, token)
    assert code == 202, job
    wait(job, token)

    def publish(number: int) -> str:
        code, result = request(
            "POST",
            "/api/v1/problems/1/publish",
            {
                "user_id": author,
                "text": f"P3 {suffix} {number}",
                "interests": ["data"],
            },
            author_token,
        )
        assert code == 202, result
        wait(result, author_token, publication=True)
        return str(result["post_id"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        ids = set(pool.map(publish, range(45)))
    path = f"/api/v1/feeds/{reader}"
    assert request("GET", path)[0] == 401
    assert request("GET", path, token=author_token)[0] == 403
    times: list[float] = []

    def page(cursor: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        code, result = request(
            "GET",
            path + ("?" + urllib.parse.urlencode({"cursor": cursor}) if cursor else ""),
            token=token,
        )
        times.append(round((time.perf_counter() - started) * 1000, 2))
        assert code == 200, result
        return dict(result)

    first = page()
    new_post = publish(46)
    second = page(first["next_cursor"])
    assert len(first["items"]) == len(second["items"]) == 20
    selected = second["items"][5]["id"]
    code, reaction = request(
        "POST",
        "/api/v1/problems/5/reaction",
        {
            "post_id": selected,
            "user_id": reader,
            "kind": "like",
        },
        token,
    )
    assert code == 202, reaction
    replay = page(first["next_cursor"])
    assert [p["id"] for p in second["items"]] == [p["id"] for p in replay["items"]]
    assert next(p for p in replay["items"] if p["id"] == selected)["reaction_count"] == 1
    third = page(second["next_cursor"])
    assert len(third["items"]) == 5 and third["next_cursor"] is None
    returned = [p["id"] for response in (first, second, third) for p in response["items"]]
    assert set(returned) == ids and len(returned) == len(set(returned))
    assert new_post in [p["id"] for p in page()["items"]]
    code, job = request("DELETE", "/api/v1/social/follows", payload, token)
    assert code == 202, job
    wait(job, token)
    assert page(first["next_cursor"])["items"] == []
    print(
        json.dumps(
            {
                "result": "OK",
                "reader": reader,
                "author": author,
                "pages": [20, 20, 5],
                "http_ms": times,
                "checks": [
                    "auth",
                    "P1/P2",
                    "cursor estable",
                    "contadores P5 actuales",
                    "sin duplicados",
                    "nuevos al refrescar",
                    "unfollow entre paginas",
                ],
                "note": "Datos QA nuevos conservados; no modifica usuarios anteriores.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
