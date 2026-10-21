"""HTTP smoke for the running API/shared P7/P8 worker. Set P8_PASSWORD after the P8 seed."""

import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

BASE = os.getenv("P8_BASE_URL", "http://127.0.0.1:8000")
TARGET = "80000000-0000-0000-0000-000000000001"
POST = "81000000-0000-0000-0000-000000000001"
HIDDEN = "81000000-0000-0000-0000-000000000002"
MOD = "80000000-0000-0000-0000-000000000002"


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
        data=None if payload is None else json.dumps(payload).encode(),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()
            return response.status, json.loads(data) if data else None
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def login(name: str) -> str:
    code, result = request(
        "POST", "/api/v1/users/login", {"username": name, "password": os.environ["P8_PASSWORD"]}
    )
    assert code == 200, result
    return str(result["access_token"])


def wait(job: dict[str, Any], token: str) -> dict[str, Any]:
    for _ in range(150):
        code, result = request(
            "GET", f"/api/v1/accounts/operations/{job['operation_id']}", token=token
        )
        assert code == 200, result
        if result["status"] in ("completed", "compensated", "failed"):
            return dict(result)
        time.sleep(0.2)
    raise AssertionError("Worker did not finish in 30 seconds")


def main() -> None:
    user, mod = login("p8_target"), login("p8_moderator")
    with urllib.request.urlopen(BASE + "/docs", timeout=10) as response:
        assert response.status == 200 and b"swagger" in response.read().lower()
    schema = request("GET", "/openapi.json")[1]
    assert schema["paths"]["/api/v1/accounts/{user_id}/suspend"]["post"]["security"]
    before = request("GET", f"/api/v1/accounts/{TARGET}/trace", token=user)[1]
    assert before["presence"] and len(before["active_conversations"]) == 1
    assert TARGET in request("GET", f"/api/v1/problems/4/recommendations/{MOD}")[1]
    path = f"/api/v1/accounts/{TARGET}/suspend"
    payload = {"reason": "P8 HTTP validation"}
    assert request("POST", path, payload)[0] == 401
    assert request("POST", path, payload, user)[0] == 403
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: request("POST", path, payload, mod, "p8-smoke-suspend"), range(2)
            )
        )
    assert all(code == 202 for code, _ in responses), responses
    assert responses[0][1]["operation_id"] == responses[1][1]["operation_id"]
    suspension = wait(responses[0][1], mod)
    assert suspension["status"] == "completed", suspension
    assert request("GET", f"/api/v1/posts/{POST}")[0] == 404
    assert request("PUT", "/api/v1/accounts/me/presence", token=user)[0] == 401
    trace = request("GET", f"/api/v1/accounts/{TARGET}/trace", token=mod)[1]
    assert trace["profile"]["account_status"] == "suspended" and not trace["presence"]
    assert trace["recent_posts"] == [] and len(trace["post_states"]) == 2
    assert TARGET not in request("GET", f"/api/v1/problems/4/recommendations/{MOD}")[1]
    assert request("GET", f"/api/v1/feeds/{MOD}", token=mod)[1]["items"] == []
    code, job = request(
        "POST", f"/api/v1/accounts/{TARGET}/reactivate", payload, mod, "p8-smoke-restore"
    )
    assert code == 202, job
    reactivation = wait(job, mod)
    assert reactivation["status"] == "completed", reactivation
    assert request("GET", f"/api/v1/posts/{POST}")[0] == 200
    assert request("GET", f"/api/v1/posts/{HIDDEN}")[0] == 404
    assert request("PUT", "/api/v1/accounts/me/presence", token=user)[0] == 401
    fresh = login("p8_target")
    assert request("PUT", "/api/v1/accounts/me/presence", token=fresh)[0] == 204
    code, job = request("POST", path, payload, mod, "p8-smoke-failure", "redis_remove_posts")
    assert code == 202, job
    compensated = wait(job, mod)
    assert compensated["status"] == "compensated", compensated
    assert request("GET", f"/api/v1/posts/{POST}")[0] == 200
    print(
        json.dumps(
            {
                "http_smoke": "passed",
                "swagger": BASE + "/docs",
                "suspension": suspension["operation_id"],
                "reactivation": reactivation["operation_id"],
                "compensated": compensated["operation_id"],
                "account": TARGET,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
