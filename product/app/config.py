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
class Settings:
    """Configuración inmutable de la aplicación.

    :param model_provider: Proveedor del modelo (solo ``fake``)
    :type model_provider: str
    :param agent_max_steps: Tope de vueltas del bucle del agente
    :type agent_max_steps: int
    :param max_question_chars: Largo máximo de la pregunta
    :type max_question_chars: int
    :param employees_path: Ruta absoluta al archivo de empleados
    :type employees_path: pathlib.Path
    """

    model_provider: str
    agent_max_steps: int
    max_question_chars: int
    employees_path: Path

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
        )
