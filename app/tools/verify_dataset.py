"""Exercise P1-P8 against seeded development accounts. This command writes demo activity."""

import argparse
import json
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.tools.dataset import Dataset, SeedOptions


class Exercise:
    def __init__(self, base_url: str, seed: int, operation_timeout: int = 600) -> None:
        self.base = base_url.rstrip("/")
        self.data = Dataset(SeedOptions(seed=seed))
        self.headers: dict[int, dict[str, str]] = {}
        self.results: dict[str, bool] = {}
        self.operation_timeout = operation_timeout

    def passed(self, problem: str) -> None:
        self.results[problem] = True
        print(json.dumps({"problem": problem, "passed": True}), flush=True)

    def request(
        self,
        method: str,
        path: str,
        actor: int | None = None,
        body: dict[str, Any] | None = None,
        expected: int = 200,
    ) -> Any:
        headers = {
            "Content-Type": "application/json",
            **(self.headers.get(actor, {}) if actor is not None else {}),
            "Idempotency-Key": str(uuid4()),
        }
        request = Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=60) as response:
                status, payload = response.status, response.read()
        except HTTPError as error:
            status, payload = error.code, error.read()
        if status != expected:
            raise RuntimeError(f"{method} {path}: HTTP {status}, esperado {expected}")
        return json.loads(payload) if payload else None

    def wait(self, path: str, actor: int | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + self.operation_timeout
        while time.monotonic() < deadline:
            result: dict[str, Any] = self.request("GET", path, actor)
            status = result.get("status", result.get("delivery_status"))
            if status == "completed":
                return result
            if status in ("failed", "compensated"):
                raise RuntimeError(f"Operación {path}: {status}")
            time.sleep(0.5)
        raise TimeoutError(f"Operación pendiente: {path}")

    def run(self, password: str) -> dict[str, bool]:
        for actor in (0, 1, 3, 4, 6):
            login = self.request(
                "POST",
                "/api/v1/users/login",
                body={"username": f"tpo{self.data.options.seed}_{actor:04d}", "password": password},
            )
            self.headers[actor] = {"Authorization": f"Bearer {login['access_token']}"}
            profile = self.request("GET", "/api/v1/users/me", actor)
            if profile["id"] != self.data.users[actor]:
                raise RuntimeError("La cuenta autenticada no pertenece al dataset esperado")
        users = self.data.users
        job = self.request(
            "POST",
            "/api/v1/posts",
            0,
            {
                "user_id": users[0],
                "text": "Demostración de los ocho problemas sobre dataset de volumen",
                "interests": ["datos"],
            },
            202,
        )
        self.wait(f"/api/v1/problems/operations/{job['operation_id']}")
        post = job["post_id"]
        preview = self.request("GET", f"/api/v1/problems/1/feed-preview/{users[1]}")
        assert post in preview["post_ids"]
        self.passed("P1")
        for method in ("DELETE", "POST"):
            follow = self.request(
                method,
                "/api/v1/social/follows",
                0,
                {"user_id": users[0], "followed_user_id": users[6]},
                202,
            )
            self.wait(f"/api/v1/social/operations/{follow['operation_id']}", 0)
        self.passed("P2")
        feed = self.request("GET", f"/api/v1/feeds/{users[1]}", 1)
        assert len(feed["items"]) == 20
        cursor = feed["next_cursor"]
        from urllib.parse import quote

        older = self.request("GET", f"/api/v1/feeds/{users[1]}?cursor={quote(cursor)}", 1)
        assert not {p["id"] for p in feed["items"]} & {p["id"] for p in older["items"]}
        self.passed("P3")
        suggestions = self.request("GET", f"/api/v1/problems/4/recommendations/{users[0]}")
        mutual = self.request(
            "GET", f"/api/v1/problems/4/mutual-friends?user_id={users[0]}&other_user_id={users[1]}"
        )
        assert 0 < len(suggestions) <= 10 and isinstance(mutual, list)
        self.passed("P4")
        for kind, payload in (
            ("reaction", {"kind": "like"}),
            ("comment", {"text": "Comentario del smoke de volumen"}),
        ):
            self.request(
                "POST",
                f"/api/v1/problems/5/{kind}",
                6,
                {"post_id": post, "user_id": users[6], **payload},
                202,
            )
        visible = self.request("GET", f"/api/v1/posts/{post}")
        assert (visible["reaction_count"], visible["comment_count"]) == (1, 1)
        self.passed("P5")
        group = self.data.groups[0]
        history = self.request("GET", f"/api/v1/messages/conversations/{group}/messages", 0)
        assert history["items"]
        message = self.request(
            "POST",
            f"/api/v1/messages/conversations/{group}/messages",
            0,
            {"text": "Mensaje nuevo sobre historial de volumen"},
            202,
        )
        self.wait(f"/api/v1/messages/{message['id']}/delivery", 0)
        self.request(
            "PUT", f"/api/v1/messages/conversations/{group}/read", 1, {"message_id": message["id"]}
        )
        self.passed("P6")
        report = self.request(
            "POST", "/api/v1/moderation/reports", 1, {"post_id": post, "reason": "other"}, 201
        )
        self.request(
            "POST", "/api/v1/moderation/reports", 6, {"post_id": post, "reason": "spam"}, 201
        )
        for action in ("decision", "revert"):
            body = {
                "reason": "Revisión de datos sintéticos",
                **({"decision": "hide"} if action == "decision" else {}),
            }
            operation = self.request(
                "POST", f"/api/v1/moderation/reports/{report['id']}/{action}", 3, body, 202
            )
            self.wait(f"/api/v1/moderation/operations/{operation['operation_id']}", 3)
            self.request(
                "GET", f"/api/v1/posts/{post}", expected=404 if action == "decision" else 200
            )
        restored = self.request("GET", f"/api/v1/posts/{post}")
        assert (restored["reaction_count"], restored["comment_count"]) == (1, 1)
        self.passed("P7")
        for action in ("suspend", "reactivate"):
            operation = self.request(
                "POST",
                f"/api/v1/accounts/{users[5]}/{action}",
                4,
                {"reason": "Demostración de volumen"},
                202,
            )
            self.wait(f"/api/v1/accounts/operations/{operation['operation_id']}", 4)
            trace = self.request("GET", f"/api/v1/accounts/{users[5]}/trace", 4)
            assert trace["profile"]["account_status"] == (
                "suspended" if action == "suspend" else "active"
            )
            self.request(
                "GET",
                f"/api/v1/posts/{self.data.posts[5]}",
                expected=404 if action == "suspend" else 200,
            )
        self.passed("P8")
        return self.results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--exercise", action="store_true", help="Ejecutar actividad real P1-P8")
    parser.add_argument("--operation-timeout", type=int, default=600)
    args = parser.parse_args()
    if not args.exercise:
        parser.print_help()
        return
    password = os.environ.get("SEED_PASSWORD", "")
    if not password:
        raise ValueError("Definí SEED_PASSWORD para las cuentas de desarrollo")
    if args.operation_timeout < 1:
        raise ValueError("operation-timeout debe ser positivo")
    print(
        json.dumps(
            Exercise(args.base_url, args.seed, args.operation_timeout).run(password), indent=2
        )
    )


if __name__ == "__main__":
    main()
