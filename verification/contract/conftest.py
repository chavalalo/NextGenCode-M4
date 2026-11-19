"""El producto corriendo, para las pruebas de contrato."""

import pytest

from verification.server import FACTORY_KEY, running_product

# Segunda clave de prueba del reto: no es un secreto, solo existe en estas corridas
ADMIN_KEY = "admin-key-0123456789"


@pytest.fixture(scope="session")
def api():
    """El producto con su configuración por omisión."""
    with running_product(8765) as client:
        yield client


@pytest.fixture(scope="session")
def api_one_step():
    """El producto con el bucle limitado a una sola vuelta."""
    with running_product(8766, AGENT_MAX_STEPS="1") as client:
        yield client


@pytest.fixture(scope="session")
def api_limited():
    """El producto con un límite de dos peticiones por minuto."""
    with running_product(8770, RATE_LIMIT_PER_MINUTE="2") as client:
        yield client


@pytest.fixture(scope="session")
def api_cached():
    """El producto con la caché de respuestas encendida (reto)."""
    with running_product(8771, ANSWER_CACHE_TTL_SECONDS="300") as client:
        yield client


@pytest.fixture(scope="session")
def api_large_down():
    """El producto con el modelo capaz caído: debe responder el de respaldo (reto)."""
    with running_product(
        8772, FAKE_UNAVAILABLE_MODELS="@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    ) as client:
        yield client


@pytest.fixture(scope="session")
def api_models_down():
    """El producto con los dos modelos caídos (reto)."""
    with running_product(
        8773,
        FAKE_UNAVAILABLE_MODELS=(
            "@cf/meta/llama-3.1-8b-instruct-fast,@cf/meta/llama-3.3-70b-instruct-fp8-fast"
        ),
    ) as client:
        yield client


@pytest.fixture(scope="session")
def api_two_clients():
    """Dos clientes; solo ``admin`` puede leer las métricas (reto)."""
    with running_product(
        8774,
        API_KEYS=f"factory:{FACTORY_KEY},admin:{ADMIN_KEY}",
        METRICS_CLIENTS="admin",
    ) as client:
        yield client
