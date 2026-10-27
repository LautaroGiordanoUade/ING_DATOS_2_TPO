"""Smoke HTTP para Problema 4: recomendaciones y amigos en común.
Requiere Docker Compose y la API iniciada.
"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4

BASE = os.getenv("P4_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_PASSWORD = os.getenv("P4_PASSWORD", "123456789")


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


def follow_and_wait(follower_id: str, followed_id: str, token: str, label: str) -> None:
    code, job = request(
        "POST",
        "/api/v1/social/follows",
        {"user_id": follower_id, "followed_user_id": followed_id},
        token=token,
    )
    assert code == 202, f"Error follow {label}: {job}"
    final = wait_operation(job["operation_id"], token)
    assert final.get("status") == "completed", f"Operacion {label} no completo: {final}"


def main() -> None:
    suffix = uuid4().hex[:8]
    password = DEFAULT_PASSWORD
    tokens: dict[str, str] = {}
    ids: dict[str, str] = {}

    print(f"[*] Creando usuarios de prueba (prefijo qa-p4-{suffix}, password={password})...")
    for role in ("usera", "userb", "common", "target", "target2"):
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
    print("    - User A sigue a Common Friend y a User B")
    follow_and_wait(ids["usera"], ids["common"], tokens["usera"], "A->Common")
    follow_and_wait(ids["usera"], ids["userb"], tokens["usera"], "A->B")

    print("    - User B sigue a Common Friend y a Target")
    follow_and_wait(ids["userb"], ids["common"], tokens["userb"], "B->Common")
    follow_and_wait(ids["userb"], ids["target"], tokens["userb"], "B->Target")

    print("    - Common Friend sigue a Target (score 2) y a Target 2 (score 1)")
    follow_and_wait(ids["common"], ids["target"], tokens["common"], "Common->Target")
    follow_and_wait(ids["common"], ids["target2"], tokens["common"], "Common->Target2")

    print("[*] Verificando amigos en común:")
    code, mutuals = request(
        "GET",
        f"/api/v1/problems/4/mutual-friends?user_id={ids['usera']}&other_user_id={ids['userb']}",
    )
    assert code == 200, f"Error mutual-friends: {mutuals}"
    assert ids["common"] in mutuals, f"Common Friend no encontrado en {mutuals}"
    assert ids["userb"] not in mutuals, "No debe incluir a uno de los usuarios consultados"
    print(f"    PASS: Amigo en común detectado exitosamente ({ids['common']})")

    code, mutuals_same = request(
        "GET",
        f"/api/v1/problems/4/mutual-friends?user_id={ids['usera']}&other_user_id={ids['usera']}",
    )
    assert code == 200 and mutuals_same == [], f"Esperado [], recibido: {mutuals_same}"
    print("    PASS: Amigos en común consigo mismo devuelve lista vacía.")

    print("[*] Verificando recomendaciones de segundo grado y orden por score:")
    code, recs = request("GET", f"/api/v1/problems/4/recommendations/{ids['usera']}")
    assert code == 200, f"Error recomendaciones: {recs}"
    assert ids["target"] in recs, f"Target no sugerido a User A en {recs}"
    assert ids["target2"] in recs, f"Target 2 no sugerido a User A en {recs}"
    assert recs.index(ids["target"]) < recs.index(ids["target2"]), (
        f"Target (score 2) debe aparecer antes que Target 2 (score 1): {recs}"
    )
    assert ids["common"] not in recs, "No debe sugerir cuentas que ya sigue (Common)"
    assert ids["userb"] not in recs, "No debe sugerir cuentas que ya sigue (User B)"
    assert ids["usera"] not in recs, "No debe sugerirse a sí mismo"
    assert len(recs) <= 10, "No debe devolver más de 10 recomendaciones"
    print(
        f"    PASS: Cuentas sugeridas y ordenadas por score ({ids['target']} -> {ids['target2']})"
    )

    print("[*] Verificando intereses editables y cambio de ranking:")
    for role in ("target2", "usera"):
        code, profile = request(
            "PUT", "/api/v1/users/me/interests", {"interests": [" Python ", "PYTHON"]}, tokens[role]
        )
        assert code == 200 and profile["interests"] == ["python"], profile
    code, updated = request("GET", f"/api/v1/problems/4/recommendations/{ids['usera']}")
    assert code == 200 and updated[:2] == [ids["target2"], ids["target"]], updated
    code, profile = request("GET", "/api/v1/users/me", token=tokens["usera"])
    assert code == 200 and profile["interests"] == ["python"], profile
    print(
        "    PASS: preferencias normalizadas y persistidas; intereses priorizados sobre conexiones"
    )
    print(json.dumps({"users": ids, "usera": f"qa-p4-{suffix}-usera", "recommendations": updated}))

    print("\n==============================================")
    print("  TODAS LAS PRUEBAS DEL PROBLEMA 4 PASARON OK ")
    print("==============================================")


if __name__ == "__main__":
    main()
