"""Agente con bucle de vueltas con tope sobre el protocolo JSON del modelo."""

import json
from dataclasses import dataclass, field

TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
STEP_CAP_ANSWER = (
    "No pude completar la respuesta. Intenta con una pregunta más concreta."
)


@dataclass
class AgentResult:
    """Resultado de una ejecución del agente.

    :param answer: Respuesta final en español
    :type answer: str
    :param steps: Número de llamadas al modelo
    :type steps: int
    :param tools_used: Herramientas ejecutadas, en orden
    :type tools_used: list[str]
    :param input_tokens: Tokens de entrada sumados entre vueltas
    :type input_tokens: int
    :param output_tokens: Tokens de salida sumados entre vueltas
    :type output_tokens: int
    """

    answer: str
    steps: int = 0
    tools_used: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class Agent:
    """Agente único que alterna entre el modelo y las herramientas del directorio.

    :param model: Modelo con el método ``complete(messages)``
    :type model: app.llm.LanguageModel
    :param directory: Directorio de empleados de solo lectura
    :type directory: app.directory.EmployeeDirectory
    :param max_steps: Tope de vueltas del bucle
    :type max_steps: int
    """

    def __init__(self, model, directory, max_steps):
        self._model = model
        self._max_steps = max_steps
        self._tools = {
            "get_employee": directory.get_employee,
            "search_by_department": directory.search_by_department,
        }

    def run(self, messages):
        """Ejecuta el bucle hasta tener respuesta o llegar al tope.

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: Respuesta, vueltas, herramientas y tokens
        :rtype: AgentResult
        """
        conversation = [dict(message) for message in messages]
        result = AgentResult(answer=STEP_CAP_ANSWER)
        for step in range(1, self._max_steps + 1):
            completion = self._model.complete(conversation)
            result.steps = step
            result.input_tokens += completion.input_tokens
            result.output_tokens += completion.output_tokens
            request = _parse(completion.text)
            if isinstance(request.get("answer"), str):
                result.answer = request["answer"]
                return result
            tool_output = self._run_tool(request, result.tools_used)
            conversation.append({"role": "assistant", "content": completion.text})
            conversation.append(
                {"role": "user", "content": TOOL_RESULT_PREFIX + tool_output}
            )
        result.answer = STEP_CAP_ANSWER
        return result

    def _run_tool(self, request, tools_used):
        """Ejecuta la herramienta pedida; los errores se devuelven como texto.

        :param request: Pedido del modelo ya interpretado
        :type request: dict
        :param tools_used: Lista donde se registran las herramientas ejecutadas
        :type tools_used: list[str]
        :return: Resultado de la herramienta o descripción del error
        :rtype: str
        """
        if "error" in request:
            return "error: " + request["error"]
        name = request.get("tool")
        tool = self._tools.get(name)
        if tool is None:
            return f"error: unknown tool {name!r}"
        args = request.get("args", {})
        if not isinstance(args, dict):
            return f"error: invalid args for tool {name!r}"
        try:
            output = tool(**args)
        except TypeError as error:
            return f"error: invalid args for tool {name!r}: {error}"
        tools_used.append(name)
        return output


def _parse(text):
    """Interpreta la respuesta del modelo como un objeto JSON.

    :param text: Texto devuelto por el modelo
    :type text: str
    :return: El objeto, o ``{"error": ...}`` si no es un objeto JSON válido
    :rtype: dict
    """
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {"error": "the model response is not valid JSON"}
    if not isinstance(value, dict):
        return {"error": "the model response is not a JSON object"}
    return value
