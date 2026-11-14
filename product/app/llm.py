"""Interfaz del modelo de lenguaje y modelo simulado determinista."""

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, Sequence

TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
ANSWER_PREFIX = "Según el directorio: "
HELP_ANSWER = "Pregúntame por un empleado (EMP-0001) o un departamento."
EMPLOYEE_ID_PATTERN = re.compile(r"\bEMP-\d{4}\b", re.IGNORECASE)


@dataclass(frozen=True)
class Completion:
    """Respuesta de un modelo con su conteo de tokens.

    :param text: Texto devuelto por el modelo (un objeto JSON)
    :type text: str
    :param input_tokens: Tokens de entrada consumidos
    :type input_tokens: int
    :param output_tokens: Tokens de salida generados
    :type output_tokens: int
    """

    text: str
    input_tokens: int
    output_tokens: int


class LanguageModel(Protocol):  # pylint: disable=too-few-public-methods
    """Interfaz común de los modelos: el agente solo conoce ``complete``."""

    def complete(self, messages: Sequence[dict]) -> Completion:
        """Genera la siguiente respuesta de la conversación.

        :param messages: Mensajes con ``role`` y ``content``
        :type messages: Sequence[dict]
        :return: Respuesta del modelo
        :rtype: Completion
        """


def _fold(text):
    """Quita acentos y pasa a minúsculas para comparar textos.

    :param text: Texto original
    :type text: str
    :return: Texto normalizado
    :rtype: str
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    ).casefold()


def count_words(text):
    """Cuenta palabras separadas por espacios, como aproximación de tokens.

    :param text: Texto a contar
    :type text: str
    :return: Número de palabras
    :rtype: int
    """
    return len(str(text).split())


class FakeModel:
    """Modelo simulado: decide con reglas fijas sobre el último mensaje.

    :param departments: Departamentos que existen en los datos
    :type departments: Sequence[str]
    """

    def __init__(self, departments):
        self._departments = tuple(departments)

    def complete(self, messages):
        """Responde con un objeto JSON según las reglas del modelo simulado.

        :param messages: Mensajes con ``role`` y ``content``
        :type messages: Sequence[dict]
        :return: Respuesta con los tokens contados por palabras
        :rtype: Completion
        """
        last = str(messages[-1]["content"]) if messages else ""
        text = json.dumps(self._decide(last), ensure_ascii=False)
        input_tokens = sum(count_words(message["content"]) for message in messages)
        return Completion(
            text=text,
            input_tokens=input_tokens,
            output_tokens=count_words(text),
        )

    def _decide(self, last):
        """Aplica las cuatro reglas en orden sobre el último mensaje.

        :param last: Contenido del último mensaje
        :type last: str
        :return: Pedido de herramienta o respuesta
        :rtype: dict
        """
        if last.startswith(TOOL_RESULT_PREFIX):
            return {"answer": ANSWER_PREFIX + last[len(TOOL_RESULT_PREFIX):]}
        match = EMPLOYEE_ID_PATTERN.search(last)
        if match:
            employee_id = match.group(0).upper()
            return {"tool": "get_employee", "args": {"employee_id": employee_id}}
        department = self._find_department(last)
        if department:
            return {
                "tool": "search_by_department",
                "args": {"department": department},
            }
        return {"answer": HELP_ANSWER}

    def _find_department(self, text):
        """Busca en el texto un departamento conocido.

        :param text: Texto donde buscar
        :type text: str
        :return: El departamento encontrado o ``None``
        :rtype: str or None
        """
        folded = _fold(text)
        for department in self._departments:
            pattern = r"\b" + re.escape(_fold(department)) + r"\b"
            if re.search(pattern, folded):
                return department
        return None


def build_model(settings, departments):
    """Construye el modelo indicado en la configuración.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param departments: Departamentos que existen en los datos
    :type departments: Sequence[str]
    :return: Modelo listo para usar
    :rtype: LanguageModel
    :raises ValueError: Si el proveedor no está soportado
    """
    if settings.model_provider == "fake":
        return FakeModel(departments)
    raise ValueError(f"Unsupported model provider: {settings.model_provider}")
