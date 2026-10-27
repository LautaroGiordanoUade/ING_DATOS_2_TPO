"""Measure real P8 suspension/reactivation on synthetic dataset accounts only."""

import argparse
import json
import os
import re
import time
from statistics import median
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import UUID, uuid4


class Benchmark:
    def __init__(self, base: str, actor: str, password: str, target: str, timeout: int) -> None:
        self.base = base.rstrip("/")
        self.token = ""
        self.target = str(UUID(target))
        self.timeout = timeout
        login = self.request(
            "POST", "/api/v1/users/login", {"username": actor, "password": password}
        )
        self.token = login["access_token"]
        profile = self.request("GET", "/api/v1/users/me")
        if profile["role"] not in ("moderator", "admin") or profile["id"] == self.target:
            raise ValueError("Se requiere moderador/admin y una cuenta objetivo diferente")

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Content-Type": "application/json", "Idempotency-Key": str(uuid4())}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = Request(
            self.base + path,
            method=method,
            headers=headers,
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            with urlopen(req, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"{method} {path}: HTTP {error.code}") from None

    def transition(self, action: str) -> tuple[float, str]:
        started = time.perf_counter()
        operation = self.request(
            "POST",
            f"/api/v1/accounts/{self.target}/{action}",
            {"reason": "Medición P8 sobre datos sintéticos"},
        )
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            job = self.request("GET", f"/api/v1/accounts/operations/{operation['operation_id']}")
            if job["status"] == "completed":
                return round(time.perf_counter() - started, 3), job["operation_id"]
            if job["status"] in ("failed", "compensated"):
                raise RuntimeError(
                    f"{action}: {job['status']}; revisar operación {job['operation_id']}"
                )
            time.sleep(0.2)
        raise TimeoutError(f"{action} sigue pendiente; no se canceló: {operation['operation_id']}")

    def round(self) -> dict[str, Any]:
        path = f"/api/v1/accounts/{self.target}/trace"
        before = self.request("GET", path)
        if not re.fullmatch(r"tpo\d+_\d{4,}", before["profile"]["username"]):
            raise ValueError("Este benchmark sólo modifica cuentas sintéticas tpo<seed>_<número>")
        if before["profile"]["account_status"] != "active":
            raise ValueError("La cuenta debe estar activa y sin operaciones previas pendientes")
        if len(before["post_states"]) >= 100:
            raise ValueError(
                "Elegí una cuenta con menos de 100 publicaciones para verificar toda la traza"
            )
        counters = {}
        for post in before["post_states"]:
            if post["publicly_visible"]:
                data = self.request("GET", f"/api/v1/posts/{post['id']}")
                counters[post["id"]] = (data["reaction_count"], data["comment_count"])
        suspended_seconds, suspend_id = self.transition("suspend")
        try:
            hidden = self.request("GET", path)
            assert hidden["profile"]["account_status"] == "suspended"
            assert all(not p["publicly_visible"] for p in hidden["post_states"])
            assert not hidden["presence"]
        finally:
            # A completed suspension is always paired with a real reactivation.
            reactivated_seconds, reactivate_id = self.transition("reactivate")
        after = self.request("GET", path)
        assert after["profile"]["account_status"] == "active"
        assert sorted(before["post_states"], key=lambda p: p["id"]) == sorted(
            after["post_states"], key=lambda p: p["id"]
        )
        for pid, expected in counters.items():
            data = self.request("GET", f"/api/v1/posts/{pid}")
            assert (data["reaction_count"], data["comment_count"]) == expected
        return {
            "posts": len(before["post_states"]),
            "suspend_seconds": suspended_seconds,
            "reactivate_seconds": reactivated_seconds,
            "state_and_counters_restored": True,
            "suspend_operation": suspend_id,
            "reactivate_operation": reactivate_id,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--actor", default="tpo42_0004")
    parser.add_argument("--target", required=True, type=str)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--exercise", action="store_true")
    args = parser.parse_args()
    if not args.exercise:
        parser.print_help()
        return
    if urlparse(args.base_url).hostname not in ("localhost", "127.0.0.1", "api"):
        raise ValueError("Usá una API local de desarrollo")
    password = os.environ.get("SEED_PASSWORD", "")
    if not password or not 1 <= args.repeats <= 10 or args.timeout < 1:
        raise ValueError("Requiere SEED_PASSWORD, repeats entre 1 y 10 y timeout positivo")
    runner = Benchmark(args.base_url, args.actor, password, args.target, args.timeout)
    rounds = []
    for _ in range(args.repeats):
        result = runner.round()
        rounds.append(result)
        print(json.dumps({"round": len(rounds), **result}), flush=True)
    print(
        json.dumps(
            {
                "rounds": rounds,
                "median_suspend_seconds": median(item["suspend_seconds"] for item in rounds),
                "median_reactivate_seconds": median(item["reactivate_seconds"] for item in rounds),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
