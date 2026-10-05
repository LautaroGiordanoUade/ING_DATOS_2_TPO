import os

import pytest


@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="Requiere motores externos configurados por el usuario",
)
def test_external_services_placeholder() -> None:
    # TODO(TP): Agregar pruebas por motor y pruebas de consistencia/compensación reales.
    assert True

