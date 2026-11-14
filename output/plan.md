# Plan del HR Assistant (sesión 2: observabilidad)

Fuente: `spec/02-observability.md`, `spec/01-architecture.md`, `QA.md`, los contratos
`verification/contract/test_contract.py` y `test_contract_02.py`, `verification/qa.py` y el
producto de la sesión 1 que ya existe en `product/`. Todo lo de la sesión 1 se conserva; este
plan indica qué se agrega y qué cambia.

## Módulos

| Archivo | Estado | Responsabilidad |
| --- | --- | --- |
| `product/app/clock.py` | nuevo | `Clock` (`Protocol` con `now() -> datetime` en UTC y `monotonic() -> float` en segundos), `SystemClock` real y `FixedClock` manual para pruebas. Único lugar que toca la hora del sistema. |
| `product/app/logs.py` | nuevo | `JsonLogger(service, clock, stream)`: `emit(event, request_id, **fields)` escribe una línea JSON (`ts`, `service`, `event`, `request_id` + campos) en el `stream` (por omisión `sys.stdout`), con candado. |
| `product/app/metrics.py` | nuevo | `Metrics(slo_p95_ms, window)`: `record_request(latency_ms, status)`, `add_tokens(input, output)` y `snapshot(pid)` con el formato de `GET /metrics`; percentiles por rango más cercano sobre una ventana acotada; con candado. |
| `product/app/tracing.py` | nuevo | `Tracer` con `wrap(fn, name, run_type)` y `context(request_id)`. `NoopTracer` sin dependencias; `LangSmithTracer` usa `langsmith.traceable` y un `Client(hide_inputs, hide_outputs)`. `build_tracer(settings)` elige uno. |
| `product/app/config.py` | cambia | Agrega `service_name`, `slo_p95_ms`, `hide_inputs`, `hide_outputs` y `tracing_enabled` (solo si `LANGSMITH_TRACING=true` y existe `LANGSMITH_API_KEY`). Nunca guarda la clave. Booleanos inválidos lanzan `ConfigError`. |
| `product/app/agent.py` | cambia | `AgentResult` suma `stopped` (`"answer"` o `"max_steps"`) y `tool_calls` (lista de `{"tool", "args"}` ejecutadas). Recibe un `tracer` opcional y envuelve `run`, `model.complete` y cada herramienta. Sigue sin conocer FastAPI ni el log. |
| `product/app/main.py` | cambia | `create_app(settings, model, directory, clock, log_stream, tracer)`. Middleware de request id, log `request`, métricas y manejo de errores 500. `POST /ask` agrega `request_id` y registra `agent_run` y `audit`. Nuevo `GET /metrics`. |
| `product/app/static/index.html` | cambia | Muestra `Id de la petición: <request_id>` en cada respuesta (y en errores, leído del encabezado `X-Request-ID`), siempre con `textContent`. |
| `product/app/directory.py` | igual | Directorio de empleados de solo lectura. |
| `product/app/llm.py` | igual | Interfaz `LanguageModel` y `FakeModel`. |
| `product/requirements.txt` | cambia | Agrega `langsmith`. |
| `product/README.md` | nuevo (developer) | Qué es, cómo correrlo y probarlo, tabla de variables de ambas sesiones. Único `.md` en la raíz del producto. |
| `product/doc/` | cambia (architect) | `architecture.md` actualizado y ADR 0004 a 0006. |

Detalles que fijan el contrato entre módulos:

- `X-Request-ID` del cliente se acepta solo si cumple `^[A-Za-z0-9._-]{1,128}$`; si no, se
  genera `str(uuid.uuid4())`. El id se guarda en `request.state.request_id`.
- `latency_ms` se calcula con `clock.monotonic()` (no con `now()`), redondeado a 1 decimal.
- `ts` = `clock.now()` en UTC con formato ISO 8601 y sufijo `Z`, con milisegundos.
- `error_rate` = respuestas con estado >= 500 / total de peticiones (0.0 si no hay). Los 4xx
  son errores del cliente y no cuentan. Se cuentan todas las rutas, incluida `/metrics`.
- Sin peticiones, `p50` y `p95` valen `0.0` y `met` es `true`. `met` = `p95 < slo_p95_ms`.
- Ventana de latencias: constante `LATENCY_WINDOW = 1000` en `metrics.py` (memoria acotada).
- `agent_run`: `question_chars = len(question)`, `history_messages = len(history)`,
  `steps`, `tools` (= `tools_used`), `input_tokens`, `output_tokens`, `stopped`.
- `error`: campo `error_type = type(exc).__name__`; nunca `str(exc)` ni la traza.
- Los logs se escriben con `json.dumps(..., ensure_ascii=False)`.

## Flujo de una pregunta

1. La persona escribe la pregunta y pulsa enviar; el JS manda `POST /ask` con
   `{"question", "history"}`.
2. El middleware lee `X-Request-ID`; si falta o es inválido genera un UUID. Toma
   `start = clock.monotonic()`.
3. FastAPI valida el cuerpo (422 si falla; el 422 también lleva `X-Request-ID` y se registra).
4. `ask` arma `messages = history + [question]` y, dentro de `tracer.context(request_id)`,
   llama a `agent.run(messages)`.
5. El agente corre el bucle con tope de la sesión 1. Con trazas encendidas, la corrida, cada
   `complete` y cada herramienta quedan como `@traceable` con `request_id` en los metadatos.
6. `ask` emite un `audit` por cada elemento de `result.tool_calls`
   (`action: "tool_call"`, `tool`, `args`) y luego un `agent_run` con los conteos; nunca texto
   de la pregunta ni de la respuesta.
7. `ask` suma los tokens a `Metrics` y responde
   `{"answer", "steps", "tools_used", "input_tokens", "output_tokens", "request_id"}`.
8. Si algo lanza una excepción, el middleware emite `error` con `error_type` y responde `500`
   con `{"detail": "internal error", "request_id": ...}`.
9. En todos los casos el middleware calcula `latency_ms`, emite `request`
   (`method`, `path`, `status`, `latency_ms`), registra en `Metrics` y pone `X-Request-ID` en
   la respuesta.
10. El JS pinta respuesta, herramientas e `Id de la petición` con `textContent`.
11. `GET /metrics` devuelve `Metrics.snapshot(os.getpid())`.

## Pruebas

Todas con `create_app()` y dependencias inyectadas (`FixedClock`, `io.StringIO` como
`log_stream`, `NoopTracer` o un tracer falso), con `TestClient`, sin red. Cobertura de 80 % o
más. Las pruebas de la sesión 1 siguen pasando sin cambios (salvo agregar `request_id`).

Escenarios Gherkin nuevos (`product/tests/features/observability.feature`):

1. Every response carries a generated request id (`GET /health` -> UUID válido).
2. The client request id is kept (`demo-123` en encabezado y en el cuerpo de `/ask`).
3. An invalid client request id is replaced (valor con espacios o de 200 caracteres -> UUID).
4. Asking writes request, agent_run and audit log lines with the same request id, and none
   contains the question or the answer text.
5. An unexpected error returns 500 with `internal error` and the request id, and logs an
   `error` line with the error type only.
6. Metrics report requests, latency percentiles, tokens and SLO after a question.
7. The SLO is not met when p95 is above `SLO_P95_MS` (reloj falso que avanza).
8. The home page shows the request id.

Pruebas unitarias nuevas o ampliadas:

- `test_clock.py`: `FixedClock` devuelve UTC y avanza solo cuando se le pide.
- `test_logs.py`: campos obligatorios; formato de `ts`; una línea por evento; acentos sin
  escapar.
- `test_metrics.py`: percentiles p50/p95 con valores conocidos; ventana acotada; `error_rate`
  solo cuenta 5xx; estado vacío; `met` en el borde (`p95 == target` -> `false`).
- `test_tracing.py`: sin clave `build_tracer` devuelve `NoopTracer` aunque
  `LANGSMITH_TRACING=true`; `NoopTracer.wrap` devuelve la misma función; con clave (y
  `langsmith` sustituido por un doble con `monkeypatch`) se pasan `hide_inputs`,
  `hide_outputs` y el `request_id` en metadatos.
- `test_config.py`: valores por omisión nuevos; `SLO_P95_MS=0` y `HIDE_INPUTS=quizas` lanzan
  `ConfigError`; `Settings` no expone la clave (ni en `repr`).
- `test_agent.py`: `stopped` vale `answer` o `max_steps`; `tool_calls` coincide con
  `tools_used`; el tracer envuelve modelo y herramientas.
- `test_api.py`: `GET /metrics` tiene exactamente las llaves del spec; `index.html` sigue sin
  `innerHTML`.

## Riesgos

| Riesgo | Cómo se evita |
| --- | --- |
| Filtrar datos personales en el log (texto de la pregunta o respuesta). | `agent_run` solo con conteos; prueba que busca el texto de la pregunta y la respuesta en todas las líneas del log. |
| Filtrar la clave de LangSmith. | `Settings` guarda solo `tracing_enabled`; `langsmith` lee la clave del entorno; prueba sobre `repr(settings)` y el log. |
| Inyección en el log o en encabezados con un `X-Request-ID` del cliente. | Patrón permitido y largo máximo; si no cumple, UUID nuevo. |
| `/metrics` contradice "sin estado" (ADR 0001). | Son contadores operativos por proceso, no estado de negocio; se reportan con `pid`; ADR 0005. |
| Memoria creciente por guardar todas las latencias. | Ventana acotada `LATENCY_WINDOW`. |
| Carreras entre hilos (FastAPI corre rutas `def` en un pool). | `threading.Lock` en `Metrics` y `JsonLogger`. |
| Pruebas no deterministas por la hora. | `Clock` inyectado; `datetime.now()` y `time.monotonic()` solo en `SystemClock`. |
| Intentos de conexión a LangSmith sin clave o en pruebas. | `NoopTracer` por omisión; `langsmith` solo se importa dentro de `LangSmithTracer`; pruebas con doble. |
| Enviar texto de preguntas a LangSmith. | `HIDE_INPUTS` y `HIDE_OUTPUTS` en `true` por omisión, pasados al `Client`. |
| El 500 filtra detalles internos. | Respuesta fija `internal error`; log con `error_type`, nunca mensaje ni traza. |
| `args` de `audit` crecen con un modelo real. | Solo herramientas ejecutadas con argumentos validados; los valores de `args` se recortan a `AUDIT_ARG_MAX_CHARS = 200`. |
| El agente se acopla al log o a LangSmith. | El agente devuelve `tool_calls` y `stopped`; `main.py` registra; el tracer se inyecta con una interfaz mínima. |
| Romper el contrato de la sesión 1. | Campos nuevos solo se agregan; se corren ambos contratos. |
| Markdown en la raíz del producto distinto de `README.md`. | Documentos en `product/doc/`; `verification qa` lo revisa. |
