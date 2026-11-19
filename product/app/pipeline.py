"""Costura del sistema multi-agente para ``POST /ask``.

Cada pregunta pasa por: guardián -> caché -> supervisor -> especialista (con
respaldo) -> revisor. Este módulo arma el resultado (``AskOutcome``) con los
tokens y el costo de todas las llamadas, escribe ``audit`` y ``agent_run`` y
suma las métricas.

``_guard`` (prompt injection y PII de entrada) y ``_review`` (PII de salida,
ids inexistentes y recorte) ya están completos. Los métodos marcados con
«Punto de conexión» son los que completan los agentes siguientes, sin cambiar
la firma:

- ``costs``: ``_cache_lookup`` y ``_cache_store`` (caché de respuestas) y
  ``_run_specialist`` (respaldo con el otro modelo).
- ``observability``: ``_record`` (contadores de negocio) y las trazas de
  ``agent.guard``, ``agent.supervisor`` y ``agent.reviewer``.
"""

from dataclasses import dataclass, field
from typing import Any

from app.costs import COST_DECIMALS
from app.guard import InputBlocked, inspect
from app.levers import choose_model, trim_history
from app.metrics import BLOCKED_INPUTS, OUTPUT_BLOCKED, PII_REDACTIONS
from app.reviewer import BLOCK_REASON as REVIEW_BLOCK_REASON
from app.reviewer import review

LOCATION_INPUT = "input"
LOCATION_OUTPUT = "output"
AGENT_GUARD = "guard"
AGENT_SUPERVISOR = "supervisor"
AGENT_REVIEWER = "reviewer"
AGENT_CACHE = "cache"
AUDIT_ARG_MAX_CHARS = 200
USER_ROLE = "user"


@dataclass(frozen=True)
class GuardedInput:
    """Entrada ya revisada por el guardián.

    :param question: Pregunta, con la PII reemplazada por marcadores
    :type question: str
    :param history: Historial completo, con la PII reemplazada
    :type history: list[dict]
    :param pii_types: Tipos de PII ocultados en la entrada
    :type pii_types: tuple[str, ...]
    """

    question: str
    history: list
    pii_types: tuple = ()


@dataclass(frozen=True)
class ReviewedAnswer:
    """Respuesta ya revisada por el revisor.

    :param answer: Respuesta final
    :type answer: str
    :param pii_types: Tipos de PII ocultados en la salida
    :type pii_types: tuple[str, ...]
    :param blocked: ``True`` si se reemplazó por el mensaje de verificación
    :type blocked: bool
    """

    answer: str
    pii_types: tuple = ()
    blocked: bool = False


@dataclass(frozen=True)
class SpecialistRun:
    """Corrida de un especialista.

    :param result: Resultado del bucle del agente
    :type result: app.agent.AgentResult
    :param model: Modelo que contestó
    :type model: str
    :param fallback: ``True`` si contestó el modelo de respaldo
    :type fallback: bool
    """

    result: Any
    model: str
    fallback: bool = False


@dataclass
class AskOutcome:  # pylint: disable=too-many-instance-attributes
    """Resultado de una pregunta: la respuesta y lo que se registra de ella.

    ``input_tokens``, ``output_tokens``, ``cached_calls`` y ``cost_usd`` suman
    supervisor y especialista; ``steps`` y ``tools_used`` son del especialista.

    :param answer: Respuesta final
    :type answer: str
    :param steps: Vueltas del especialista
    :type steps: int
    :param tools_used: Herramientas del especialista, en orden
    :type tools_used: list[str]
    :param input_tokens: Tokens de entrada
    :type input_tokens: int
    :param output_tokens: Tokens de salida
    :type output_tokens: int
    :param model: Modelo que contestó
    :type model: str
    :param route: Motivo del enrutador de costo
    :type route: str
    :param cached_calls: Llamadas respondidas desde la caché del gateway
    :type cached_calls: int
    :param cost_usd: Costo en USD
    :type cost_usd: float
    :param specialist: ``directory`` o ``policy``
    :type specialist: str
    :param agents: Agentes que corrieron, en orden
    :type agents: list[str]
    :param supervisor_route: Motivo del supervisor
    :type supervisor_route: str
    :param pii_redacted: Tipos de PII ocultados, sin repetir y ordenados
    :type pii_redacted: list[str]
    :param cached: ``True`` si salió de la caché de respuestas
    :type cached: bool
    :param fallback: ``True`` si contestó el modelo de respaldo
    :type fallback: bool
    :param stopped: Por qué terminó el especialista
    :type stopped: str
    :param tool_calls: Herramientas con sus argumentos, para el ``audit``
    :type tool_calls: list[dict]
    :param history_sent: Mensajes de historial que se mandaron al modelo
    :type history_sent: int
    :param output_blocked: ``True`` si el revisor reemplazó la respuesta
    :type output_blocked: bool
    """

    answer: str
    steps: int
    tools_used: list
    input_tokens: int
    output_tokens: int
    model: str
    route: str
    cached_calls: int
    cost_usd: float
    specialist: str
    agents: list
    supervisor_route: str
    pii_redacted: list = field(default_factory=list)
    cached: bool = False
    fallback: bool = False
    stopped: str = "answer"
    tool_calls: list = field(default_factory=list)
    history_sent: int = 0
    output_blocked: bool = False

    def response_fields(self):
        """Campos de la respuesta de ``POST /ask`` (sin ``request_id``).

        :return: Valores por nombre de campo
        :rtype: dict
        """
        return {
            "answer": self.answer,
            "steps": self.steps,
            "tools_used": list(self.tools_used),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model": self.model,
            "route": self.route,
            "cached_calls": self.cached_calls,
            "cost_usd": self.cost_usd,
            "specialist": self.specialist,
            "agents": list(self.agents),
            "supervisor_route": self.supervisor_route,
            "pii_redacted": list(self.pii_redacted),
            "cached": self.cached,
            "fallback": self.fallback,
        }


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


def _sum_tokens(completions):
    """Suma tokens y llamadas cacheadas de varias llamadas al modelo.

    :param completions: Llamadas al modelo
    :type completions: Iterable[app.completion.Completion]
    :return: Tokens de entrada, de salida y llamadas cacheadas
    :rtype: tuple[int, int, int]
    """
    input_tokens = output_tokens = cached_calls = 0
    for completion in completions:
        input_tokens += completion.input_tokens
        output_tokens += completion.output_tokens
        cached_calls += 1 if completion.cached else 0
    return input_tokens, output_tokens, cached_calls


@dataclass(frozen=True)
class PipelineDependencies:  # pylint: disable=too-many-instance-attributes
    """Dependencias ya construidas del pipeline.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param models: Modelos por nombre (``MODEL_SMALL`` y ``MODEL_LARGE``)
    :type models: dict[str, app.llm.LanguageModel]
    :param prices: Tabla de precios por modelo
    :type prices: app.costs.PriceTable
    :param supervisor: Supervisor que elige el especialista
    :type supervisor: app.supervisor.Supervisor
    :param specialists: Especialistas por nombre
    :type specialists: dict[str, app.agent.Agent]
    :param directory: Directorio de empleados (lo usa el revisor)
    :type directory: app.directory.EmployeeDirectory
    :param tracer: Tracer de la corrida
    :type tracer: app.tracing.NoopTracer or app.tracing.LangSmithTracer
    :param logger: Log JSON
    :type logger: app.logs.JsonLogger
    :param metrics: Métricas del proceso
    :type metrics: app.metrics.Metrics
    """

    settings: object
    models: dict
    prices: object
    supervisor: object
    specialists: dict
    directory: object
    tracer: object
    logger: object
    metrics: object


class AskPipeline:
    """Orquesta los agentes de una pregunta.

    :param dependencies: Dependencias ya construidas
    :type dependencies: PipelineDependencies
    """

    def __init__(self, dependencies):
        self._deps = dependencies

    def answer(self, request_id, client, payload):
        """Responde una pregunta pasando por todos los agentes.

        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente que pregunta
        :type client: str
        :param payload: Cuerpo de ``POST /ask`` (``question`` y ``history``)
        :type payload: pydantic.BaseModel
        :return: Respuesta y datos de la corrida
        :rtype: AskOutcome
        :raises app.gateway.ModelUnavailable: Si ningún modelo contesta
        """
        deps = self._deps
        history = [message.model_dump() for message in payload.history]
        with deps.tracer.context(request_id, client=client):
            guarded = self._guard(request_id, client, payload.question, history)
            outcome = self._cache_lookup(guarded)
            if outcome is None:
                outcome = self._answer_with_agents(request_id, client, guarded)
                self._cache_store(guarded, outcome)
        self._record(request_id, client, payload, outcome)
        return outcome

    def _answer_with_agents(self, request_id, client, guarded):
        """Supervisor, especialista y revisor; arma tokens y costo.

        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente que pregunta
        :type client: str
        :param guarded: Entrada ya revisada por el guardián
        :type guarded: GuardedInput
        :return: Resultado de la pregunta
        :rtype: AskOutcome
        :raises app.gateway.ModelUnavailable: Si ningún modelo contesta
        """
        deps = self._deps
        settings = deps.settings
        decision = deps.supervisor.route(guarded.question)
        route = choose_model(guarded.question, settings)
        history = trim_history(guarded.history, settings.history_window)
        messages = history + [{"role": USER_ROLE, "content": guarded.question}]
        run = self._run_specialist(
            deps.specialists[decision.specialist], messages, route.model
        )
        reviewed = self._review(request_id, client, run.result.answer)
        input_tokens, output_tokens, cached_calls = _sum_tokens(
            list(decision.completions) + list(run.result.completions)
        )
        return AskOutcome(
            answer=reviewed.answer,
            steps=run.result.steps,
            tools_used=list(run.result.tools_used),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=run.model,
            route=route.reason,
            cached_calls=cached_calls,
            cost_usd=self._cost(decision, run),
            specialist=decision.specialist,
            agents=[
                AGENT_GUARD,
                AGENT_SUPERVISOR,
                decision.specialist,
                AGENT_REVIEWER,
            ],
            supervisor_route=decision.route,
            pii_redacted=sorted(set(guarded.pii_types) | set(reviewed.pii_types)),
            fallback=run.fallback,
            stopped=run.result.stopped,
            tool_calls=list(run.result.tool_calls),
            history_sent=len(history),
            output_blocked=reviewed.blocked,
        )

    def _cost(self, decision, run):
        """Costo de la pregunta: supervisor (modelo pequeño) más especialista.

        :param decision: Decisión del supervisor con sus llamadas
        :type decision: app.supervisor.Decision
        :param run: Corrida del especialista con el modelo que contestó
        :type run: SpecialistRun
        :return: Costo en USD
        :rtype: float
        """
        prices = self._deps.prices
        total = prices.cost(
            self._deps.settings.model_small, decision.completions
        ) + prices.cost(run.model, run.result.completions)
        return round(total, COST_DECIMALS)

    def _guard(self, request_id, client, question, history):
        """Guardián de entrada.

        Bloquea prompt injection con ``InputBlocked`` antes de llamar a
        cualquier modelo y redacta la PII de la pregunta y del historial. El
        ``audit`` lleva solo motivo, tipos y conteo: nunca el texto.

        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente que pregunta
        :type client: str
        :param question: Pregunta original
        :type question: str
        :param history: Historial original
        :type history: list[dict]
        :return: Entrada revisada
        :rtype: GuardedInput
        :raises app.guard.InputBlocked: Si hay prompt injection
        """
        deps = self._deps
        try:
            result = inspect(question, history)
        except InputBlocked as blocked:
            deps.logger.emit(
                "audit",
                request_id,
                client=client,
                action="input_blocked",
                reason=blocked.reason,
            )
            deps.metrics.add_security(BLOCKED_INPUTS)
            raise
        self._audit_pii(request_id, client, LOCATION_INPUT, result)
        return GuardedInput(
            question=result.question,
            history=result.history,
            pii_types=tuple(result.types),
        )

    def _audit_pii(self, request_id, client, location, redaction):
        """Escribe el ``audit`` de PII y suma el contador, si hubo PII.

        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente que pregunta
        :type client: str
        :param location: ``input`` u ``output``
        :type location: str
        :param redaction: Resultado con ``types`` y ``count``
        :type redaction: app.guard.GuardResult or app.reviewer.Review
        """
        if not redaction.count:
            return
        self._deps.logger.emit(
            "audit",
            request_id,
            client=client,
            action="pii_redacted",
            location=location,
            types=list(redaction.types),
            count=redaction.count,
        )
        self._deps.metrics.add_security(PII_REDACTIONS, redaction.count)

    def _cache_lookup(self, guarded):  # pylint: disable=unused-argument
        """Busca la respuesta en la caché de respuestas.

        Punto de conexión (costs): solo con ``ANSWER_CACHE_TTL_SECONDS > 0``,
        sin historial y sin PII; un acierto devuelve ``agents: ["guard",
        "cache"]``, costo, pasos y tokens en 0 y ``cached: True``.

        :param guarded: Entrada ya revisada por el guardián
        :type guarded: GuardedInput
        :return: Resultado desde la caché o ``None`` si no hay acierto
        :rtype: AskOutcome or None
        """
        return None

    def _cache_store(self, guarded, outcome):  # pylint: disable=unused-argument
        """Guarda una respuesta candidata en la caché de respuestas.

        Punto de conexión (costs): solo respuestas con ``stopped == "answer"``,
        sin bloqueo del revisor y sin respaldo.

        :param guarded: Entrada ya revisada por el guardián
        :type guarded: GuardedInput
        :param outcome: Resultado recién calculado
        :type outcome: AskOutcome
        """

    def _run_specialist(self, agent, messages, model_name):
        """Corre el especialista con el modelo elegido por el enrutador.

        Punto de conexión (costs): si el modelo sigue caído y
        ``MODEL_FALLBACK=true``, repetir una vez con el otro modelo y marcar
        ``fallback=True``.

        :param agent: Especialista elegido
        :type agent: app.agent.Agent
        :param messages: Historial recortado y pregunta, ya redactados
        :type messages: list[dict]
        :param model_name: Modelo que eligió el enrutador de costo
        :type model_name: str
        :return: Resultado del especialista y modelo que contestó
        :rtype: SpecialistRun
        :raises app.gateway.ModelUnavailable: Si el modelo no contesta
        """
        result = agent.run(messages, model=self._deps.models[model_name])
        return SpecialistRun(result=result, model=model_name)

    def _review(self, request_id, client, answer):
        """Revisor de salida.

        Redacta la PII de la respuesta, reemplaza las que citan ids
        ``EMP-dddd`` inexistentes y recorta a ``MAX_ANSWER_CHARS``. El
        ``audit`` lleva solo tipos, conteo y motivo: nunca la respuesta.

        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente que pregunta
        :type client: str
        :param answer: Respuesta del especialista
        :type answer: str
        :return: Respuesta revisada
        :rtype: ReviewedAnswer
        """
        deps = self._deps
        result = review(answer, deps.directory, deps.settings.max_answer_chars)
        self._audit_pii(request_id, client, LOCATION_OUTPUT, result)
        if result.blocked:
            deps.logger.emit(
                "audit",
                request_id,
                client=client,
                action="output_blocked",
                reason=REVIEW_BLOCK_REASON,
            )
            deps.metrics.add_security(OUTPUT_BLOCKED)
        return ReviewedAnswer(
            answer=result.answer,
            pii_types=tuple(result.types),
            blocked=result.blocked,
        )

    def _record(self, request_id, client, payload, outcome):
        """Escribe ``audit`` por herramienta y ``agent_run``; suma métricas.

        Solo conteos, tipos, modelo y costo: nunca el texto de la pregunta ni
        de la respuesta. Punto de conexión (observability): contadores por
        especialista, cliente, caché, supervisor y respaldo.

        :param request_id: Id de la petición
        :type request_id: str
        :param client: Nombre del cliente que pregunta
        :type client: str
        :param payload: Cuerpo de ``POST /ask``
        :type payload: pydantic.BaseModel
        :param outcome: Resultado de la pregunta
        :type outcome: AskOutcome
        """
        deps = self._deps
        for call in outcome.tool_calls:
            deps.logger.emit(
                "audit",
                request_id,
                client=client,
                action="tool_call",
                tool=call["tool"],
                args=_audit_args(call["args"]),
            )
        deps.logger.emit(
            "agent_run",
            request_id,
            question_chars=len(payload.question),
            history_messages=len(payload.history),
            steps=outcome.steps,
            tools=list(outcome.tools_used),
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            stopped=outcome.stopped,
            client=client,
            model=outcome.model,
            route=outcome.route,
            history_sent=outcome.history_sent,
            cached_calls=outcome.cached_calls,
            cost_usd=outcome.cost_usd,
            specialist=outcome.specialist,
            agents=list(outcome.agents),
            supervisor_route=outcome.supervisor_route,
            pii_types=list(outcome.pii_redacted),
            cached=outcome.cached,
            fallback=outcome.fallback,
        )
        deps.metrics.add_tokens(outcome.input_tokens, outcome.output_tokens)
        deps.metrics.add_cost(outcome.cost_usd)
