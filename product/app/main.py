"""API web sin estado del HR Assistant.

``create_app`` recibe sus dependencias para que las pruebas inyecten las suyas;
``app`` es la instancia que arranca uvicorn con la configuración del entorno.

Cada petición lleva un id (``X-Request-ID``), deja una línea JSON en el log y
se cuenta en las métricas del proceso.
"""

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.agent import Agent
from app.clock import SystemClock
from app.config import Settings
from app.directory import EmployeeDirectory
from app.llm import build_model
from app.logs import JsonLogger
from app.metrics import Metrics
from app.tracing import build_tracer

INDEX_PATH = Path(__file__).resolve().parent / "static" / "index.html"
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")
AUDIT_ARG_MAX_CHARS = 200
INTERNAL_ERROR_STATUS = 500
INTERNAL_ERROR_DETAIL = "internal error"


class HistoryMessage(BaseModel):
    """Mensaje previo de la conversación que guarda el navegador.

    :param role: ``user`` o ``assistant``
    :type role: str
    :param content: Texto del mensaje
    :type content: str
    """

    role: Literal["user", "assistant"]
    content: str


class AskResponse(BaseModel):
    """Respuesta de ``POST /ask``.

    :param answer: Respuesta en español
    :type answer: str
    :param steps: Vueltas que dio el agente
    :type steps: int
    :param tools_used: Herramientas usadas, en orden
    :type tools_used: list[str]
    :param input_tokens: Tokens de entrada
    :type input_tokens: int
    :param output_tokens: Tokens de salida
    :type output_tokens: int
    :param request_id: Id de la petición, para pasarlo a soporte
    :type request_id: str
    """

    answer: str
    steps: int
    tools_used: List[str]
    input_tokens: int
    output_tokens: int
    request_id: str


@dataclass(frozen=True)
class _Runtime:
    """Dependencias ya construidas que usan las rutas.

    :param agent: Agente que responde las preguntas
    :type agent: app.agent.Agent
    :param tracer: Tracer de la corrida
    :type tracer: app.tracing.NoopTracer or app.tracing.LangSmithTracer
    :param logger: Log JSON
    :type logger: app.logs.JsonLogger
    :param metrics: Métricas del proceso
    :type metrics: app.metrics.Metrics
    :param ask_request: Clase Pydantic del cuerpo de ``POST /ask``
    :type ask_request: type
    :param index_html: Página web
    :type index_html: str
    """

    agent: Agent
    tracer: object
    logger: JsonLogger
    metrics: Metrics
    ask_request: type
    index_html: str


def _build_ask_request(max_question_chars):
    """Crea el modelo de la petición con el largo máximo configurado.

    :param max_question_chars: Largo máximo de la pregunta
    :type max_question_chars: int
    :return: Clase Pydantic de la petición
    :rtype: type
    """

    class AskRequest(BaseModel):
        """Cuerpo de ``POST /ask``.

        :param question: Pregunta de la persona
        :type question: str
        :param history: Vueltas anteriores enviadas por el cliente
        :type history: list[HistoryMessage]
        """

        question: str = Field(max_length=max_question_chars)
        history: List[HistoryMessage] = Field(default_factory=list)

        @field_validator("question")
        @classmethod
        def question_not_blank(cls, value):
            """Rechaza preguntas vacías o solo con espacios.

            :param value: Pregunta recibida
            :type value: str
            :return: La pregunta sin cambios
            :rtype: str
            :raises ValueError: Si la pregunta está vacía
            """
            if not value.strip():
                raise ValueError("question must not be empty")
            return value

    return AskRequest


def resolve_request_id(header_value):
    """Usa el id del cliente si es válido; si no, genera un UUID.

    Solo se aceptan letras, dígitos, ``.``, ``_`` y ``-``, hasta 128
    caracteres, para que el id no pueda inyectar nada en el log ni en los
    encabezados.

    :param header_value: Valor del encabezado ``X-Request-ID`` o ``None``
    :type header_value: str or None
    :return: Id de la petición
    :rtype: str
    """
    if header_value and REQUEST_ID_PATTERN.fullmatch(header_value):
        return header_value
    return str(uuid.uuid4())


def _audit_args(args):
    """Recorta los argumentos de una herramienta para el log de auditoría.

    :param args: Argumentos con que se llamó la herramienta
    :type args: dict
    :return: Argumentos con los textos recortados a ``AUDIT_ARG_MAX_CHARS``
    :rtype: dict
    """
    return {
        key: value[:AUDIT_ARG_MAX_CHARS] if isinstance(value, str) else value
        for key, value in args.items()
    }


def _log_agent_run(logger, request_id, payload, result):
    """Escribe un ``audit`` por herramienta y el ``agent_run`` de la corrida.

    Solo se registran conteos: nunca el texto de la pregunta ni de la respuesta.

    :param logger: Log JSON
    :type logger: app.logs.JsonLogger
    :param request_id: Id de la petición
    :type request_id: str
    :param payload: Cuerpo de la petición
    :type payload: pydantic.BaseModel
    :param result: Resultado del agente
    :type result: app.agent.AgentResult
    """
    for call in result.tool_calls:
        logger.emit(
            "audit",
            request_id,
            action="tool_call",
            tool=call["tool"],
            args=_audit_args(call["args"]),
        )
    logger.emit(
        "agent_run",
        request_id,
        question_chars=len(payload.question),
        history_messages=len(payload.history),
        steps=result.steps,
        tools=list(result.tools_used),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        stopped=result.stopped,
    )


def _install_observability(application, clock, logger, metrics):
    """Agrega el middleware de id, log ``request``, métricas y errores 500.

    :param application: Aplicación FastAPI
    :type application: fastapi.FastAPI
    :param clock: Reloj inyectado para medir la latencia
    :type clock: app.clock.Clock
    :param logger: Log JSON
    :type logger: app.logs.JsonLogger
    :param metrics: Métricas del proceso
    :type metrics: app.metrics.Metrics
    """

    @application.middleware("http")
    async def observe_request(request: Request, call_next):
        """Asigna el id, mide la latencia y convierte errores en 500."""
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        start = clock.monotonic()
        try:
            response = await call_next(request)
        except Exception as error:  # pylint: disable=broad-exception-caught
            # Solo el tipo: el mensaje puede traer datos personales.
            logger.emit("error", request_id, error_type=type(error).__name__)
            response = JSONResponse(
                status_code=INTERNAL_ERROR_STATUS,
                content={"detail": INTERNAL_ERROR_DETAIL, "request_id": request_id},
            )
        latency_ms = round((clock.monotonic() - start) * 1000, 1)
        logger.emit(
            "request",
            request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
        )
        metrics.record_request(latency_ms, response.status_code)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _add_routes(application, runtime):
    """Registra las rutas de la API.

    :param application: Aplicación FastAPI
    :type application: fastapi.FastAPI
    :param runtime: Dependencias ya construidas
    :type runtime: _Runtime
    """
    ask_request = runtime.ask_request

    @application.get("/", response_class=HTMLResponse)
    def home():
        """Sirve la página web."""
        return HTMLResponse(runtime.index_html)

    @application.get("/health")
    def health():
        """Informa que el proceso está vivo y su id."""
        return {"status": "ok", "pid": os.getpid()}

    @application.get("/metrics")
    def metrics():
        """Devuelve las métricas de este proceso."""
        return runtime.metrics.snapshot(os.getpid())

    @application.post("/ask", response_model=AskResponse)
    def ask(payload: ask_request, request: Request):
        """Responde una pregunta; el historial lo manda el cliente."""
        request_id = request.state.request_id
        messages = [message.model_dump() for message in payload.history]
        messages.append({"role": "user", "content": payload.question})
        with runtime.tracer.context(request_id):
            result = runtime.agent.run(messages)
        _log_agent_run(runtime.logger, request_id, payload, result)
        runtime.metrics.add_tokens(result.input_tokens, result.output_tokens)
        return AskResponse(
            answer=result.answer,
            steps=result.steps,
            tools_used=list(result.tools_used),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            request_id=request_id,
        )


# Las dependencias de observabilidad se inyectan por nombre para las pruebas.
# pylint: disable-next=too-many-arguments
def create_app(
    settings=None,
    model=None,
    directory=None,
    *,
    clock=None,
    log_stream=None,
    tracer=None,
):
    """Arma la aplicación FastAPI con sus dependencias.

    :param settings: Configuración; si falta se lee del entorno
    :type settings: app.config.Settings or None
    :param model: Modelo de lenguaje; si falta se construye según la configuración
    :type model: app.llm.LanguageModel or None
    :param directory: Directorio de empleados; si falta se carga del archivo
    :type directory: app.directory.EmployeeDirectory or None
    :param clock: Reloj para el log y la latencia; si falta, el del sistema
    :type clock: app.clock.Clock or None
    :param log_stream: Destino del log JSON; si falta, la salida estándar
    :type log_stream: typing.TextIO or None
    :param tracer: Tracer; si falta se elige según la configuración
    :type tracer: app.tracing.NoopTracer or app.tracing.LangSmithTracer or None
    :return: Aplicación lista para servir
    :rtype: fastapi.FastAPI
    :raises app.config.ConfigError: Si la configuración del entorno es inválida
    """
    settings = settings or Settings.from_env(os.environ)
    directory = directory or EmployeeDirectory(settings.employees_path)
    model = model or build_model(settings, directory.departments())
    clock = clock if clock is not None else SystemClock()
    tracer = tracer if tracer is not None else build_tracer(settings)
    runtime = _Runtime(
        agent=Agent(
            model=model,
            directory=directory,
            max_steps=settings.agent_max_steps,
            tracer=tracer,
        ),
        tracer=tracer,
        logger=JsonLogger(settings.service_name, clock, log_stream),
        metrics=Metrics(settings.slo_p95_ms),
        ask_request=_build_ask_request(settings.max_question_chars),
        index_html=INDEX_PATH.read_text(encoding="utf-8"),
    )

    application = FastAPI(title="HR Assistant")
    _install_observability(application, clock, runtime.logger, runtime.metrics)
    _add_routes(application, runtime)
    return application


app = create_app()
