"""Interfaz del modelo de lenguaje, modelo simulado y fábrica de modelos."""

import json
import re
import unicodedata
from typing import Protocol, Sequence

from app.completion import Completion
from app.gateway import GatewayModel
from app.policies import phrase_pattern
from app.prompts import POLICY_PROMPT, SUPERVISOR_PROMPT

__all__ = [
    "Completion",
    "FakeModel",
    "GatewayModel",
    "LanguageModel",
    "build_models",
    "count_words",
]

TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
ANSWER_PREFIX = "Según el directorio: "
POLICY_ANSWER_PREFIX = "Según la política: "
HELP_ANSWER = "Pregúntame por un empleado (EMP-0001) o un departamento."
EMPLOYEE_ID_PATTERN = re.compile(r"\bEMP-\d{4}\b", re.IGNORECASE)
FAKE_MODEL_NAME = "fake"


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


def _system_prompt(messages):
    """Devuelve el prompt de sistema del primer mensaje, si lo hay.

    :param messages: Mensajes con ``role`` y ``content``
    :type messages: Sequence[dict]
    :return: Contenido del mensaje ``system`` inicial o ``None``
    :rtype: str or None
    """
    if messages and messages[0].get("role") == "system":
        return messages[0].get("content")
    return None


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

    El nombre solo sirve para cobrarlo con el precio de ese modelo; dos
    modelos simulados con nombres distintos responden igual.

    :param departments: Departamentos que existen en los datos
    :type departments: Sequence[str]
    :param name: Nombre del modelo, como en la tabla de precios
    :type name: str
    """

    def __init__(self, departments, name=FAKE_MODEL_NAME, policy_keywords=None):
        self._departments = tuple(departments)
        self.name = name
        self._policy_patterns = tuple(
            (phrase_pattern(keyword), topic)
            for keyword, topic in dict(policy_keywords or {}).items()
        )

    def complete(self, messages):
        """Responde con un objeto JSON según las reglas del modelo simulado.

        El papel sale del prompt de sistema del primer mensaje: con
        ``SUPERVISOR_PROMPT`` clasifica la pregunta; con ``POLICY_PROMPT``
        responde como especialista de políticas; si no, como el de directorio.

        :param messages: Mensajes con ``role`` y ``content``
        :type messages: Sequence[dict]
        :return: Respuesta con los tokens contados por palabras
        :rtype: Completion
        """
        last = str(messages[-1]["content"]) if messages else ""
        system = _system_prompt(messages)
        if system == SUPERVISOR_PROMPT:
            decision = self._classify(last)
        else:
            prefix = POLICY_ANSWER_PREFIX if system == POLICY_PROMPT else ANSWER_PREFIX
            decision = self._decide(last, prefix)
        text = json.dumps(decision, ensure_ascii=False)
        input_tokens = sum(count_words(message["content"]) for message in messages)
        return Completion(
            text=text,
            input_tokens=input_tokens,
            output_tokens=count_words(text),
        )

    def _classify(self, last):
        """Papel de supervisor: ``policy`` si hay palabra clave de política.

        :param last: Pregunta a clasificar
        :type last: str
        :return: Especialista elegido
        :rtype: dict
        """
        topic = self._find_policy_topic(last)
        return {"specialist": "policy" if topic else "directory"}

    def _decide(self, last, prefix=ANSWER_PREFIX):
        """Aplica las reglas en orden sobre el último mensaje.

        Resultado de herramienta, id de empleado, departamento, palabra clave de
        una política y, si nada aplica, el texto de ayuda.

        :param last: Contenido del último mensaje
        :type last: str
        :param prefix: Inicio de la respuesta con el resultado de la herramienta
        :type prefix: str
        :return: Pedido de herramienta o respuesta
        :rtype: dict
        """
        if last.startswith(TOOL_RESULT_PREFIX):
            return {"answer": prefix + last[len(TOOL_RESULT_PREFIX):]}
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
        topic = self._find_policy_topic(last)
        if topic:
            return {"tool": "search_policy", "args": {"topic": topic}}
        return {"answer": HELP_ANSWER}

    def _find_policy_topic(self, text):
        """Busca en el texto una palabra clave de política.

        :param text: Texto donde buscar
        :type text: str
        :return: Tema de la política o ``None``
        :rtype: str or None
        """
        folded = _fold(text)
        for pattern, topic in self._policy_patterns:
            if pattern.search(folded):
                return topic
        return None

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


def build_models(settings, departments, http_client=None, policy_keywords=None):
    """Construye el modelo barato y el capaz según la configuración.

    Con ``fake`` son dos modelos simulados con los nombres de ``MODEL_SMALL`` y
    ``MODEL_LARGE``; con ``gateway`` son dos modelos reales de AI Gateway.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param departments: Departamentos que existen en los datos
    :type departments: Sequence[str]
    :param http_client: Cliente HTTP para el gateway; si falta se crea uno
    :type http_client: httpx.Client or None
    :param policy_keywords: Tema por palabra clave de política, para el modelo
        simulado
    :type policy_keywords: Mapping[str, str] or None
    :return: Modelos por nombre
    :rtype: dict[str, LanguageModel]
    :raises ValueError: Si el proveedor no está soportado
    """
    # Punto de conexión (costs): FAKE_UNAVAILABLE_MODELS y reintentos.
    names = (settings.model_small, settings.model_large)
    if settings.model_provider == "fake":
        return {
            name: FakeModel(departments, name, policy_keywords) for name in names
        }
    if settings.model_provider == "gateway":
        return {name: GatewayModel(name, settings, http_client) for name in names}
    raise ValueError(f"Unsupported model provider: {settings.model_provider}")
