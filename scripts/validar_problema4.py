"""Smoke HTTP para Problema 4: recomendaciones y amigos en común.
Requiere Docker Compose y la API iniciada.
"""

import json
import os
import secrets
import time
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4

BASE = os.getenv("P4_BASE_URL", "http://127.0.0.1:8000")


def request(
    method: str, path: str, payload: dict[str, Any] | None = None, token: str | None = None
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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
        data = exc.read()
        return exc.code, json.loads(data) if data else None


def wait_operation(operation_id: str, token: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        code, result = request("GET", f"/api/v1/social/operations/{operation_id}", token=token)
        if code == 200 and result.get("status") in ("completed", "failed", "compensated"):
            return dict(result)
        time.sleep(0.3)
    raise TimeoutError(f"Operacion {operation_id} no finalizo a tiempo")


def main() -> None:
    suffix = uuid4().hex[:8]
    password = secrets.token_urlsafe(16)
    tokens: dict[str, str] = {}
    ids: dict[str, str] = {}

    print(f"[*] Creando usuarios de prueba (prefijo qa-p4-{suffix})...")
    # Roles: userA, userB, commonFriend, suggestedTarget
    for role in ("usera", "userb", "common", "target"):
        username = f"qa-p4-{suffix}-{role}"
        code, body = request(
            "POST",
            "/api/v1/users",
            {
                "username": username,
                "full_name": f"QA {role}",
                "email": f"{username}@test.local",
                "password": password,
                "account_type": "public",
            },
        )
        assert code == 201, f"Fallo al crear usuario {username}: {body}"
        ids[role] = body["id"]

        code, auth = request(
            "POST",
            "/api/v1/users/login",
            {"username": username, "password": password},
        )
        assert code == 200, f"Fallo login {username}: {auth}"
        tokens[role] = auth["access_token"]

    print("[*] Configurando grafo social:")
    print("    - User A sigue a Common Friend")
    code, job_a = request(
        "POST",
        "/api/v1/social/follows",
        {"user_id": ids["usera"], "followed_user_id": ids["common"]},
        token=tokens["usera"],
    )
    assert code == 202, f"Error follow A->Common: {job_a}"
    wait_operation(job_a["operation_id"], tokens["usera"])

    print("    - User B sigue a Common Friend")
    code, job_b = request(
        "POST",
        "/api/v1/social/follows",
        {"user_id": ids["userb"], "followed_user_id": ids["common"]},
        token=tokens["userb"],
    )
    assert code == 202, f"Error follow B->Common: {job_b}"
    wait_operation(job_b["operation_id"], tokens["userb"])

    print("    - Common Friend sigue a Target (segundo grado para User A)")
    code, job_c = request(
        "POST",
        "/api/v1/social/follows",
        {"user_id": ids["common"], "followed_user_id": ids["target"]},
        token=tokens["common"],
    )
    assert code == 202, f"Error follow Common->Target: {job_c}"
    wait_operation(job_c["operation_id"], tokens["common"])

    print("[*] Verificando amigos en común:")
    code, mutuals = request(
        "GET",
        f"/api/v1/problems/4/mutual-friends?user_id={ids['usera']}&other_user_id={ids['userb']}",
    )
    assert code == 200, f"Error mutual-friends: {mutuals}"
    assert ids["common"] in mutuals, f"Common Friend no encontrado en {mutuals}"
    print(f"    PASS: Amigo en común detectado exitosamente ({ids['common']})")

    code, mutuals_same = request(
        "GET",
        f"/api/v1/problems/4/mutual-friends?user_id={ids['usera']}&other_user_id={ids['usera']}",
    )
    assert code == 200 and mutuals_same == [], f"Esperado [], recibido: {mutuals_same}"
    print("    PASS: Amigos en común consigo mismo devuelve lista vacía.")

    print("[*] Verificando recomendaciones de segundo grado:")
    code, recs = request("GET", f"/api/v1/problems/4/recommendations/{ids['usera']}")
    assert code == 200, f"Error recomendaciones: {recs}"
    assert ids["target"] in recs, f"Target no sugerido a User A en {recs}"
    assert ids["common"] not in recs, "No debe sugerir cuentas que ya sigue"
    assert len(recs) <= 10, "No debe devolver más de 10 recomendaciones"
    print(f"    PASS: Cuenta sugerida correctamente por segundo grado ({ids['target']})")

    print("\n==============================================")
    print("  TODAS LAS PRUEBAS DEL PROBLEMA 4 PASARON OK ")
    print("==============================================")


if __name__ == "__main__":
    main()
