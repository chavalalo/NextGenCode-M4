"""Fixtures compartidas: arman la aplicación con dependencias inyectadas.

Ninguna prueba usa red ni servidor: todo pasa por ``create_app()`` y
``fastapi.testclient.TestClient``.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, then

PRODUCT = Path(__file__).resolve().parents[1]
if str(PRODUCT) not in sys.path:
    sys.path.insert(0, str(PRODUCT))

# pylint: disable=wrong-import-position
from app.config import Settings  # noqa: E402
from app.directory import EmployeeDirectory  # noqa: E402
from app.llm import FakeModel  # noqa: E402
from app.main import create_app  # noqa: E402

DATA_PATH = PRODUCT / "data" / "employees.json"


@pytest.fixture
def directory():
    """Directorio real de empleados, leído de ``product/data/employees.json``."""
    return EmployeeDirectory(DATA_PATH)


@pytest.fixture
def fake_model(directory):
    """Modelo simulado que conoce los departamentos del directorio."""
    return FakeModel(directory.departments())


@pytest.fixture
def make_client(directory):
    """Fábrica de clientes HTTP con configuración y modelo a elección.

    :return: Función que recibe variables de entorno y un modelo opcional
    :rtype: callable
    """

    def _make(environ=None, model=None):
        settings = Settings.from_env(environ or {})
        chosen = model or FakeModel(directory.departments())
        app = create_app(settings=settings, model=chosen, directory=directory)
        return TestClient(app)

    return _make


# Pasos Gherkin compartidos por todos los escenarios.


@given("the HR assistant is running", target_fixture="client")
def running_assistant(make_client):
    """Aplicación con la configuración por omisión y el modelo simulado."""
    return make_client()


@then(parsers.parse("the response status is {status:d}"))
def response_status_is(response, status):
    """Comprueba el código HTTP de la última respuesta."""
    assert response.status_code == status
