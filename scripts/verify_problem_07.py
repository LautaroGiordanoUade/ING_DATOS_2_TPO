"""HTTP-only P7 smoke test. Run seed_problem_07.py --reset first; set P7_PASSWORD."""

import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

BASE = os.getenv("P7_BASE_URL", "http://localhost:8000")
PASSWORD = os.environ["P7_PASSWORD"]


def request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    fail_at: str | None = None,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if fail_at:
        headers["X-Fail-At-Step"] = fail_at
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers=headers,
        data=None if payload is None else json.dumps(payload).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def login(username: str) -> str:
    code, body = request(
        "POST", "/api/v1/users/login", {"username": username, "password": PASSWORD}
    )
    assert code == 200, body
    return str(body["access_token"])


def wait(job: dict[str, Any], token: str) -> dict[str, Any]:
    for _ in range(150):
        code, result = request(
            "GET", "/api/v1/moderation/operations/" + job["operation_id"], token=token
        )
        assert code == 200, result
        if result["status"] in ("completed", "compensated", "failed"):
            return dict(result)
        time.sleep(0.2)
    raise AssertionError("Worker did not finish within 30 seconds")


def main() -> None:
    user, moderator, admin = (login("p7_" + role) for role in ("user", "moderator", "admin"))
    assert request("GET", "/health/ready")[0] == 200
    with urllib.request.urlopen(BASE + "/docs", timeout=10) as response:
        assert response.status == 200 and b"swagger" in response.read().lower()
    schema = request("GET", "/openapi.json")[1]
    assert schema["paths"]["/api/v1/moderation/reports/{report_id}/decision"]["post"]["security"]
    records: list[dict[str, Any]] = []
    for number, action in ((1, "hide"), (2, "reject"), (3, "hide"), (4, "hide")):
        post_id = f"71000000-0000-0000-0000-{number:012d}"
        assert request("GET", f"/api/v1/posts/{post_id}")[0] == 200
        code, report = request(
            "POST",
            "/api/v1/moderation/reports",
            {"post_id": post_id, "reason": "spam", "description": "P7 HTTP smoke"},
            user,
        )
        assert code == 201, report
        path = f"/api/v1/moderation/reports/{report['id']}/decision"
        payload = {"decision": action, "reason": "Smoke validation"}
        assert request("POST", path, payload)[0] == 401
        assert request("POST", path, payload, user)[0] == 403
        if number == 4:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(request, "POST", path, payload, moderator),
                    executor.submit(
                        request, "POST", path, {"decision": "reject", "reason": "Conflict"}, admin
                    ),
                ]
                responses = [future.result() for future in futures]
            assert sorted(code for code, _ in responses) == [202, 409], responses
            job = next(body for code, body in responses if code == 202)
        else:
            code, job = request(
                "POST", path, payload, moderator, "redis_feed" if number == 3 else None
            )
            assert code == 202, job
        result = wait(job, moderator)
        assert result["status"] == ("compensated" if number == 3 else "completed"), result
        state = request("GET", f"/api/v1/moderation/posts/{post_id}/state", token=moderator)[1]
        hidden = result["action"] == "hide" and number != 3
        assert request("GET", f"/api/v1/posts/{post_id}")[0] == (404 if hidden else 200)
        assert state["counters"] == {
            "post_reactions": 0 if hidden else 2,
            "post_comments": 0 if hidden else 1,
        }, state
        feed = request("GET", "/api/v1/feeds/70000000-0000-0000-0000-000000000001")[1]
        assert (post_id in [post["id"] for post in feed["items"]]) == (not hidden)
        if number == 1:
            for _ in range(2):
                code, revert = request(
                    "POST",
                    f"/api/v1/moderation/reports/{report['id']}/revert",
                    {"reason": "Allowed on review"},
                    admin,
                )
                assert code == 202, revert
                assert wait(revert, moderator)["status"] == "completed"
            restored = request("GET", f"/api/v1/posts/{post_id}")[1]
            assert restored["reaction_count"] == 2 and restored["comment_count"] == 1
            history = request("GET", f"/api/v1/moderation/history/{post_id}", token=moderator)[1]
            assert len(history) == 2
        records.append(
            {
                "post_id": post_id,
                "report_id": report["id"],
                "operation_id": job["operation_id"],
                "status": result["status"],
            }
        )
    print(
        json.dumps({"http_smoke": "passed", "swagger": BASE + "/docs", "cases": records}, indent=2)
    )


if __name__ == "__main__":
    main()
