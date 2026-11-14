"""Configuración del HR Assistant leída de variables de entorno.

La configuración es inmutable y se valida completa al construirse: un valor
inválido impide arrancar con un mensaje claro.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PRODUCT_DIR = Path(__file__).resolve().parents[1]
SUPPORTED_PROVIDERS = ("fake",)

DEFAULT_MODEL_PROVIDER = "fake"
DEFAULT_AGENT_MAX_STEPS = "3"
DEFAULT_MAX_QUESTION_CHARS = "2000"
DEFAULT_EMPLOYEES_PATH = "data/employees.json"
DEFAULT_SERVICE_NAME = "hr-assistant"
DEFAULT_SLO_P95_MS = "2000"
DEFAULT_LANGSMITH_TRACING = "false"
DEFAULT_HIDE_TEXT = "true"
BOOLEAN_VALUES = {"true": True, "false": False}


class ConfigError(ValueError):
    """Error de configuración: algún valor de entorno no es válido."""


def _positive_int(environ, name, default):
    """Lee una variable de entorno como entero mayor que cero.

    :param environ: Variables de entorno
    :type environ: Mapping[str, str]
    :param name: Nombre de la variable
    :type name: str
    :param default: Valor por omisión en texto
    :type default: str
    :return: El entero leído
    :rtype: int
    :raises ConfigError: Si el valor no es un entero mayor que cero
    """
    raw = environ.get(name, default)
    try:
        value = int(str(raw).strip())
    except ValueError as error:
        raise ConfigError(
            f"{name} must be a positive integer, got {raw!r}"
        ) from error
    if value <= 0:
        raise ConfigError(f"{name} must be greater than 0, got {value}")
    return value


def _boolean(environ, name, default):
    """Lee una variable de entorno como ``true`` o ``false``.

    :param environ: Variables de entorno
    :type environ: Mapping[str, str]
    :param name: Nombre de la variable
    :type name: str
    :param default: Valor por omisión en texto
    :type default: str
    :return: El booleano leído
    :rtype: bool
    :raises ConfigError: Si el valor no es ``true`` ni ``false``
    """
    raw = environ.get(name, default)
    value = BOOLEAN_VALUES.get(str(raw).strip().lower())
    if value is None:
        raise ConfigError(f"{name} must be 'true' or 'false', got {raw!r}")
    return value


def _service_name(environ):
    """Lee el nombre del servicio para el log.

    :param environ: Variables de entorno
    :type environ: Mapping[str, str]
    :return: Nombre del servicio sin espacios a los lados
    :rtype: str
    :raises ConfigError: Si el nombre está vacío
    """
    name = str(environ.get("SERVICE_NAME", DEFAULT_SERVICE_NAME)).strip()
    if not name:
        raise ConfigError("SERVICE_NAME must not be empty")
    return name


def _tracing_enabled(environ):
    """Decide si se trazan corridas en LangSmith.

    Solo se trazan si ``LANGSMITH_TRACING`` vale ``true`` y existe la clave.
    La clave solo se consulta para saber si existe; nunca se guarda.

    :param environ: Variables de entorno
    :type environ: Mapping[str, str]
    :return: ``True`` si las trazas están encendidas
    :rtype: bool
    :raises ConfigError: Si ``LANGSMITH_TRACING`` no es ``true`` ni ``false``
    """
    requested = _boolean(environ, "LANGSMITH_TRACING", DEFAULT_LANGSMITH_TRACING)
    has_key = bool(str(environ.get("LANGSMITH_API_KEY", "")).strip())
    return requested and has_key


def _employees_path(environ):
    """Resuelve la ruta del archivo de empleados y comprueba que exista.

    Las rutas relativas se resuelven contra la carpeta ``product/``.

    :param environ: Variables de entorno
    :type environ: Mapping[str, str]
    :return: Ruta absoluta al archivo de empleados
    :rtype: pathlib.Path
    :raises ConfigError: Si el archivo no existe
    """
    raw = environ.get("EMPLOYEES_PATH", DEFAULT_EMPLOYEES_PATH)
    path = Path(raw)
    if not path.is_absolute():
        path = PRODUCT_DIR / path
    path = path.resolve()
    if not path.is_file():
        raise ConfigError(f"EMPLOYEES_PATH does not point to a file: {path}")
    return path


@dataclass(frozen=True)
class Settings:  # pylint: disable=too-many-instance-attributes
    """Configuración inmutable de la aplicación.

    :param model_provider: Proveedor del modelo (solo ``fake``)
    :type model_provider: str
    :param agent_max_steps: Tope de vueltas del bucle del agente
    :type agent_max_steps: int
    :param max_question_chars: Largo máximo de la pregunta
    :type max_question_chars: int
    :param employees_path: Ruta absoluta al archivo de empleados
    :type employees_path: pathlib.Path
    :param service_name: Campo ``service`` del log
    :type service_name: str
    :param slo_p95_ms: Meta de latencia p95 en milisegundos
    :type slo_p95_ms: int
    :param hide_inputs: No mandar entradas a LangSmith
    :type hide_inputs: bool
    :param hide_outputs: No mandar salidas a LangSmith
    :type hide_outputs: bool
    :param tracing_enabled: Trazas encendidas (``LANGSMITH_TRACING`` y clave)
    :type tracing_enabled: bool
    """

    model_provider: str
    agent_max_steps: int
    max_question_chars: int
    employees_path: Path
    service_name: str = DEFAULT_SERVICE_NAME
    slo_p95_ms: int = int(DEFAULT_SLO_P95_MS)
    hide_inputs: bool = True
    hide_outputs: bool = True
    tracing_enabled: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        """Construye la configuración a partir de variables de entorno.

        :param environ: Variables de entorno (por ejemplo ``os.environ``)
        :type environ: Mapping[str, str]
        :return: Configuración validada
        :rtype: Settings
        :raises ConfigError: Si algún valor es inválido
        """
        provider = environ.get("MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER).strip()
        if provider not in SUPPORTED_PROVIDERS:
            raise ConfigError(
                f"MODEL_PROVIDER must be one of {SUPPORTED_PROVIDERS}, "
                f"got {provider!r}"
            )
        return cls(
            model_provider=provider,
            agent_max_steps=_positive_int(
                environ, "AGENT_MAX_STEPS", DEFAULT_AGENT_MAX_STEPS
            ),
            max_question_chars=_positive_int(
                environ, "MAX_QUESTION_CHARS", DEFAULT_MAX_QUESTION_CHARS
            ),
            employees_path=_employees_path(environ),
            service_name=_service_name(environ),
            slo_p95_ms=_positive_int(environ, "SLO_P95_MS", DEFAULT_SLO_P95_MS),
            hide_inputs=_boolean(environ, "HIDE_INPUTS", DEFAULT_HIDE_TEXT),
            hide_outputs=_boolean(environ, "HIDE_OUTPUTS", DEFAULT_HIDE_TEXT),
            tracing_enabled=_tracing_enabled(environ),
        )
