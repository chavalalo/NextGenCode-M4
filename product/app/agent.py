"""Agente con bucle de vueltas con tope sobre el protocolo JSON del modelo."""

import json
from dataclasses import dataclass, field

from app.tracing import NoopTracer

TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
STOPPED_ANSWER = "answer"
STOPPED_MAX_STEPS = "max_steps"
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
    :param stopped: Por qué terminó: ``answer`` o ``max_steps``
    :type stopped: str
    :param tool_calls: Herramientas ejecutadas con sus argumentos
    :type tool_calls: list[dict]
    """

    answer: str
    steps: int = 0
    tools_used: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stopped: str = STOPPED_MAX_STEPS
    tool_calls: list = field(default_factory=list)


class Agent:
    """Agente único que alterna entre el modelo y las herramientas del directorio.

    :param model: Modelo con el método ``complete(messages)``
    :type model: app.llm.LanguageModel
    :param directory: Directorio de empleados de solo lectura
    :type directory: app.directory.EmployeeDirectory
    :param max_steps: Tope de vueltas del bucle
    :type max_steps: int
    :param tracer: Tracer que envuelve la corrida, el modelo y las herramientas;
        si falta no se traza nada
    :type tracer: app.tracing.NoopTracer or None
    """

    def __init__(self, model, directory, max_steps, tracer=None):
        tracer = tracer if tracer is not None else NoopTracer()
        self._complete = tracer.wrap(model.complete, "model.complete", "llm")
        self._max_steps = max_steps
        self._tools = {
            name: tracer.wrap(tool, name, "tool")
            for name, tool in (
                ("get_employee", directory.get_employee),
                ("search_by_department", directory.search_by_department),
            )
        }
        self._traced_loop = tracer.wrap(self._loop, "agent.run", "chain")

    def run(self, messages):
        """Ejecuta el bucle hasta tener respuesta o llegar al tope.

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: Respuesta, vueltas, herramientas, tokens y motivo de término
        :rtype: AgentResult
        """
        return self._traced_loop(messages)

    def _loop(self, messages):
        """Bucle con tope del agente (la parte que se traza como ``chain``).

        :param messages: Conversación con ``role`` y ``content``
        :type messages: list[dict]
        :return: Respuesta, vueltas, herramientas, tokens y motivo de término
        :rtype: AgentResult
        """
        conversation = [dict(message) for message in messages]
        result = AgentResult(answer=STEP_CAP_ANSWER)
        for step in range(1, self._max_steps + 1):
            completion = self._complete(conversation)
            result.steps = step
            result.input_tokens += completion.input_tokens
            result.output_tokens += completion.output_tokens
            request = _parse(completion.text)
            if isinstance(request.get("answer"), str):
                result.answer = request["answer"]
                result.stopped = STOPPED_ANSWER
                return result
            tool_output = self._run_tool(request, result)
            conversation.append({"role": "assistant", "content": completion.text})
            conversation.append(
                {"role": "user", "content": TOOL_RESULT_PREFIX + tool_output}
            )
        result.answer = STEP_CAP_ANSWER
        result.stopped = STOPPED_MAX_STEPS
        return result

    def _run_tool(self, request, result):
        """Ejecuta la herramienta pedida; los errores se devuelven como texto.

        :param request: Pedido del modelo ya interpretado
        :type request: dict
        :param result: Resultado donde se registran las herramientas ejecutadas
        :type result: AgentResult
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
        result.tools_used.append(name)
        result.tool_calls.append({"tool": name, "args": dict(args)})
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
