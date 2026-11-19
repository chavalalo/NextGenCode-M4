# Plan del HR Assistant (reto: sistema multi-agente en producción)

Fuente: `spec/05-reto.md`, las especificaciones 01 a 04, `spec/policies.json`, el contrato
`verification/contract/test_contract_05.py` (y su `conftest.py`), `verification/evaluate.py`,
`verification/load.py`, `verification/server.py`, `verification/qa.py`, `hooks/permissions.py` y
el producto publicado en `product/`. Nada de las sesiones 1 a 4 se rompe: los contratos 01 a 04
siguen igual y la ruta de una pregunta de directorio con regla cuesta lo mismo que hoy.

## Reparto y orden de trabajo

Varios agentes escriben en `product/app/` y no pueden tocar el mismo archivo a la vez. Por eso
la cadena de la aplicación es **secuencial** y en paralelo solo van los agentes que no comparten
archivos (`deploy` y `qa-e2e` nunca tocan `product/app/`).

| Fase | Agente | Archivos que toca | En paralelo con |
| --- | --- | --- | --- |
| 0 | `qa-unit` | `product/tests/` (pruebas nuevas, ajustes de pruebas viejas que la spec cambia) | nadie |
| 1 | `developer` | `app/config.py`, `prompts.py`, `policies.py`, `supervisor.py`, `specialists.py`, `pipeline.py`, `agent.py`, `llm.py` (simulado), `gateway.py` (prompt por rol), `directory.py`, `main.py` (campos nuevos, `/ready`), `data/policies.json` | `deploy`, `qa-e2e` |
| 2 | `security` | `app/pii.py`, `guard.py`, `reviewer.py`, `auth.py`, `compliance.py`, `gateway.py` (`CF_AIG_TOKEN`), `pipeline.py` (guard y revisor), `main.py` (400, 403, auditoría), `static/index.html`, `.env.example`, `README.md` (su sección), `doc/compliance-checklist.md` | `deploy`, `qa-e2e` |
| 3 | `costs` | `app/cache.py`, `resilience.py`, `clock.py` (`sleep`), `llm.py` (`FAKE_UNAVAILABLE_MODELS`, envoltura de reintentos), `gateway.py` (`retryable`), `pipeline.py` (caché y respaldo), `main.py` (cableado), `.env.example`, `README.md` (su sección) | `deploy`, `qa-e2e` |
| 4 | `observability` | `app/tracing.py`, `metrics.py`, `pipeline.py` (trazas, contadores, `agent_run`), `main.py` (`/metrics`, `/dashboard`), `static/dashboard.html`, `README.md` (versión final) | `deploy`, `qa-e2e` |
| 1-4 | `deploy` | `render.yaml`, `scripts/load_test.py`, `scripts/cost_report.py`, `.github/workflows/ci.yml` | toda la cadena |
| 1-4 | `qa-e2e` | `product/e2e/` | toda la cadena |
| 5 | `architect` | `doc/security.md`, `doc/costs.md`, `doc/operations.md` (con la tabla de `evaluate` y la salida de `load`) | nadie |

Por qué este orden: `developer` crea las costuras (`pipeline.py`, `AskOutcome`, toda la
configuración nueva) y deja a cada especialista sus módulos propios. `security` va antes que
`costs` porque la caché debe saber si hubo PII. `observability` va al final porque cuenta lo que
hacen todos (bloqueos, caché, respaldo). Los archivos compartidos (`pipeline.py`, `main.py`,
`gateway.py`, `llm.py`, `README.md`, `.env.example`) se tocan uno tras otro, nunca a la vez.
`deploy` y `qa-e2e` trabajan con los nombres de campos, eventos y `data-testid` fijados aquí.
Al cerrar cada fase corre `verification unit` (las pruebas de fases siguientes siguen en rojo).

## Módulos

| Archivo de `product/app/` | Estado | Dueño | Responsabilidad |
| --- | --- | --- | --- |
| `config.py` | cambia | developer | Lee y valida las 10 variables nuevas (tabla de la spec) y `METRICS_CLIENTS` (nombres `[A-Za-z0-9._-]`); `FAKE_UNAVAILABLE_MODELS` con otro proveedor es `ConfigError`; `cf_aig_token` con `repr=False`. |
| `prompts.py` | nuevo | developer | Prompts de sistema `DIRECTORY_PROMPT` (el actual `SYSTEM_PROMPT`), `POLICY_PROMPT` y `SUPERVISOR_PROMPT`. |
| `policies.py` | nuevo | developer | `PolicyBook.load(path)`; `find_topic(text)` por palabra clave normalizada con límite de palabra; `search_policy(topic)` devuelve el texto o «Temas disponibles: ...». |
| `supervisor.py` | nuevo | developer | `Supervisor.route(question) -> Decision(specialist, route, completions)`: reglas (`rule:employee` > `rule:department` > `rule:policy`); si no, `MODEL_SMALL` con `SUPERVISOR_PROMPT`; JSON inválido o modelo caído -> `directory` con `model_invalid`. |
| `specialists.py` | nuevo | developer | `build_specialists(directory, policies, max_steps, tracer)` -> `{"directory": Agent, "policy": Agent}` con sus herramientas y prompt. |
| `pipeline.py` | nuevo | developer, security, costs, observability | `AskPipeline.answer(request_id, client, payload) -> AskOutcome`: guard -> caché -> supervisor -> especialista (con respaldo) -> revisor; arma tokens, costo y `agents`. |
| `agent.py` | cambia | developer | `Agent(model, tools, max_steps, tracer, name, system_prompt=None)`; el constructor viejo con `directory=` sigue funcionando; la traza se llama `agent.<name>`. |
| `llm.py` | cambia | developer, costs | `FakeModel`: con `SUPERVISOR_PROMPT` responde `{"specialist": ...}`; con palabra clave de política pide `search_policy`. `build_models` acepta `policy_keywords`; aplica `FAKE_UNAVAILABLE_MODELS` y envuelve con reintentos (costs). |
| `gateway.py` | cambia | developer, security, costs | Si el primer mensaje es `system`, lo usa en lugar del prompt por omisión; manda `cf-aig-authorization: Bearer <token>` si hay `CF_AIG_TOKEN`; `ModelUnavailable.retryable` (timeout, 429, 5xx). |
| `directory.py` | cambia | developer | Agrega `has_employee(employee_id)` para el revisor y `count()` para `/ready`. |
| `pii.py` | nuevo | security | `redact(text) -> Redaction(text, types, count)`; orden email, curp, rfc, card (con Luhn), nss, phone; marcadores `[EMAIL]`... |
| `guard.py` | nuevo | security | `inspect(question, history) -> GuardResult`; `InputBlocked` ante prompt injection (frases normalizadas, solo mensajes `user`); redacta pregunta e historial. |
| `reviewer.py` | nuevo | security | `review(answer, directory, max_chars) -> Review`: PII -> id `EMP-dddd` inexistente (mensaje fijo) -> recorte a `MAX_ANSWER_CHARS`. |
| `auth.py` | cambia | security | `can_read_metrics(client, metrics_clients)`: vacía = todos. |
| `compliance.py` | cambia | security | Regla nueva en producción: `METRICS_CLIENTS` no vacía y cada nombre en `API_KEYS`. |
| `cache.py` | nuevo | costs | `normalize_question` (minúsculas, sin acentos, espacios colapsados); `AnswerCache(ttl, max_entries, clock)` con `OrderedDict` y candado; sale la más vieja. |
| `resilience.py` | nuevo | costs | `RetryingModel(model, retries, backoff, sleep)` (espera `backoff * 2**i`); `other_model(name, settings)`; `run_with_fallback`. |
| `clock.py` | cambia | costs | `sleep(seconds)`: real en `SystemClock`; `FixedClock.sleep` solo avanza el reloj. |
| `tracing.py` | cambia | observability | Run raíz `request` y `tracer.agent(name, specialist)` para `agent.guard`, `agent.supervisor`, `agent.<especialista>`, `agent.reviewer`; metadatos `request_id`, `client`, `specialist`. |
| `metrics.py` | cambia | observability | `record_answer(outcome)`, contadores de seguridad, caché, respaldos y supervisor; todo bajo el candado. |
| `main.py` | cambia | developer, security, costs, observability | `AskResponse` con 6 campos nuevos; `/ready`, `/dashboard`; 400 del guardián con `request_id`; 403 en `/metrics`; delega en `AskPipeline`. |
| `static/index.html` | cambia | security | `data-testid="assistant-answer"` en cada vuelta del asistente; texto de ayuda menciona políticas. |
| `static/dashboard.html` | nuevo | observability | Tablero sin datos en el HTML; clave en `sessionStorage` (misma llave que la página); `/metrics` cada 10 s. |
| `costs.py`, `levers.py`, `logs.py`, `ratelimit.py`, `errors.py`, `completion.py` | igual | - | Lo de las sesiones 1 a 4. |

Fuera de `app/`: `data/policies.json` (copia exacta de `spec/policies.json`, developer);
`scripts/load_test.py`, `scripts/cost_report.py`, `render.yaml`, `ci.yml` (deploy).

Reglas que fijan el contrato entre módulos:

- **Respuesta de `POST /ask`.** Además de lo actual: `specialist`, `agents`, `supervisor_route`,
  `pii_redacted` (tipos de entrada y salida, sin repetir, en orden alfabético), `cached`,
  `fallback`. `input_tokens`, `output_tokens` y `cost_usd` suman supervisor y especialista; `steps`
  y `tools_used` son del especialista; `model` es el que contestó.
- **Supervisor.** Reglas sobre la pregunta ya redactada: `EMP-\d{4}` (sin mayúsculas) ->
  `rule:employee`; departamento existente -> `rule:department`; palabra clave de política ->
  `rule:policy`. Si ninguna aplica, una llamada a `MODEL_SMALL` con `[system: SUPERVISOR_PROMPT,
  user: pregunta]` (sin historial). `ROUTING` sigue eligiendo el modelo del especialista.
- **Guardián.** Frases en una tupla constante, comparadas sin acentos ni mayúsculas y con `\s+`
  entre palabras: «ignora/olvida las instrucciones», «ignore (all|the)? previous instructions»,
  «revela tu prompt», «prompt del sistema», «system prompt», «actua como», «act as», «modo
  desarrollador», «developer mode», «jailbreak». Respuesta `400 {"detail": "request blocked by
  input policy", "request_id": ...}` (JSONResponse, no `HTTPException`); no se llama a ningún
  modelo. Orden: 401 -> 429 -> 422 -> 400.
- **PII.** `email`; `curp` (18 caracteres con su forma); `rfc` (12 o 13); `card` (13 a 19 dígitos
  con espacios o guiones que pasan Luhn); `nss` (11 dígitos); `phone` (10 dígitos con `+52`
  opcional y separadores). Límites de dígito con `(?<!\d)` y `(?!\d)` para que un patrón no se
  coma parte de otro. `EMP-0001` nunca es PII.
- **Revisor.** Mensaje exacto: «No pude verificar la respuesta con el directorio. Intenta de
  nuevo.». Recorte a `MAX_ANSWER_CHARS` al final.
- **Resiliencia.** `MODEL_RETRIES` reintentos (3 intentos con el valor 2) solo si
  `retryable`; el respaldo corre el especialista **una vez** con el otro modelo; `fallback: true`
  y `model` del que contestó; si también falla, `502 {"detail": "model unavailable"}`. Los
  modelos de `FAKE_UNAVAILABLE_MODELS` lanzan `ModelUnavailable` sin reintentos (las
  verificaciones no esperan). `CF_AIG_TOKEN` nunca en log, traza, error ni `repr`.
- **`/ready`** (sin clave): `200 {"status": "ready", "checks": {"directory": "ok", "policies":
  "ok", "prices": "ok"}}`; si algo falla, `503` con `"status": "not_ready"` y `"error"` en ese
  check. `/health` no cambia.
- **Mínimo privilegio.** `/metrics`: 401 -> 429 -> `403 {"detail": "forbidden"}` si
  `METRICS_CLIENTS` no está vacía y no nombra al cliente.
- **Auditoría** (`audit` con `client` y `action`): `tool_call`; `input_blocked` con `reason:
  prompt_injection`; `pii_redacted` con `location` (`input` u `output`), `types` y `count`;
  `output_blocked` con `reason: unknown_employee_id`; `access_denied` con `path`;
  `metrics_read`. Nunca texto de pregunta, respuesta ni valores de PII.
- **Caché.** Solo si `ANSWER_CACHE_TTL_SECONDS > 0`, historial vacío, sin PII en la entrada.
  Se guarda solo una respuesta 200 con `stopped == "answer"`, sin bloqueo del revisor y sin
  respaldo. Un acierto responde la misma `answer`, `specialist`, `supervisor_route`, `model` y
  `route`; `cached: true`, `cost_usd: 0`, `steps: 0`, tokens 0, `tools_used: []`, `agents:
  ["guard", "cache"]`. La caché es compartida entre clientes (todos ven los mismos datos).
- **Log `agent_run`.** Agrega `specialist`, `agents`, `supervisor_route`, `pii_types`, `cached`,
  `fallback`. También se escribe en los aciertos de caché (así `cost_report.py` calcula la tasa).
- **`/metrics`.** Agrega `by_specialist` y `by_client` (`{nombre: {"requests", "cost_usd"}}`,
  respuestas 200 de `/ask`, también las de caché), `security` (`blocked_inputs`,
  `pii_redactions` = valores ocultados, `output_blocked`, `access_denied`), `cache` (`hits`,
  `misses`, `hit_rate` = hits / (hits + misses), 0.0 sin consultas), `fallbacks` (respuestas del
  modelo de respaldo) y `supervisor` (`rule`, `model`; `model_invalid` cuenta como `model`).
- **Tablero.** `GET /dashboard` sin clave ni datos. `data-testid`: `dashboard`, `dashboard-key`,
  `dashboard-requests`, `dashboard-error-rate`, `dashboard-p95` (con el SLO),
  `dashboard-cost` (total y por petición), `dashboard-cache-hit-rate`, `dashboard-specialists`,
  `dashboard-clients`, `dashboard-security`. 401 -> «Clave inválida»; 403 -> «Sin permiso para
  ver métricas». Solo `textContent`, nunca `innerHTML`.
- **Despliegue.** `render.yaml`: `METRICS_CLIENTS` con `sync: false`,
  `ANSWER_CACHE_TTL_SECONDS: "300"` y `healthCheckPath: /ready`; `CF_AIG_TOKEN` y
  `LANGSMITH_API_KEY` no van en el Blueprint (se agregan en Render > Environment si se usan).
  `load_test.py <url> [--requests 60] [--concurrency 10]` con `SMOKE_API_KEY`; imprime códigos,
  p50, p95, rps y costo total; código 1 si hay `5xx`, 2 sin clave. `cost_report.py [archivo]`
  (o stdin) resume líneas `agent_run` por cliente, especialista y modelo, más la tasa de caché;
  ignora líneas que no son JSON. CI: pylint también sobre `scripts`, y en el trabajo `e2e`, tras
  Playwright, `python scripts/load_test.py $BASE_URL` contra el producto simulado.

## Flujo de una pregunta

1. La persona escribe su clave (`sessionStorage`) y su pregunta; la página manda `POST /ask` con
   `X-API-Key`, `question` y `history`.
2. El middleware asigna `request_id` y toma el tiempo; `require_client` responde 401 o 429.
3. FastAPI valida el cuerpo (422). Se abre el run raíz `request` con `request_id` y `client`.
4. **guard**: si hay prompt injection en la pregunta o en un `user` del historial -> audit
   `input_blocked`, contador `blocked_inputs`, `400`. Si no, redacta PII (audit `pii_redacted`
   con `location: input`).
5. **caché**: si aplica y hay acierto vigente -> respuesta con `agents: ["guard", "cache"]`
   (salta al paso 10). Si no, cuenta un `miss`.
6. **supervisor**: elige `directory` o `policy` por regla o con `MODEL_SMALL`.
7. `choose_model` (sesión 3) elige el modelo del especialista y `trim_history` recorta el
   historial redactado.
8. **especialista** (`agent.directory` o `agent.policy`) corre su bucle con tope; el gateway
   reintenta con espera; si el modelo sigue caído y `MODEL_FALLBACK=true`, se repite una vez con
   el otro modelo; si falla, `502`.
9. **reviewer**: redacta PII de la respuesta, bloquea ids inexistentes (`output_blocked`) y
   recorta. Si es candidata, se guarda en la caché.
10. Se escriben `audit` por herramienta y `agent_run`; las métricas suman por especialista,
    cliente, caché, supervisor y respaldo; la respuesta sale con los campos nuevos.
11. El middleware escribe `request`; la página muestra la respuesta en `assistant-answer`.

Arranque: `Settings.from_env` valida todo -> `compliance.enforce` (incluye `METRICS_CLIENTS`) ->
se cargan directorio, políticas y precios; un error impide arrancar con `ConfigError`.

## Pruebas

`qa-unit` (fase 0), con `create_app()`, dependencias inyectadas, reloj fijo y sin red; cobertura
de 80 % o más. Entre 15 y 25 pruebas nuevas. Antes ajusta las pruebas viejas que la spec cambia
a propósito: `ask.feature` (EMP-9999 ahora muestra el mensaje del revisor) y los escenarios con
«Hola» del gateway simulado (ahora hay una llamada de clasificación antes del especialista; las
aserciones de tokens y costo deben sumar ambas).

Escenarios Gherkin nuevos (`tests/features/multiagent.feature` y `guardrails.feature`):

1. An employee question goes guard, supervisor, directory, reviewer with route `rule:employee`.
2. A vacation question is answered by the policy specialist with `search_policy`.
3. A question without a rule is classified by the small model (and an invalid reply falls back
   to `directory` with `model_invalid`).
4. Prompt injection in the question or in the history returns 400 and no model is called
   (Scenario Outline con 3 frases, una en mayúsculas y una sin acentos).
5. Personal data is replaced before the model sees it and never appears in the log (Outline por
   tipo).
6. An answer with an unknown employee id is replaced by the verification message.
7. A repeated question without history comes from the cache with cost 0.
8. When the large model is down the small one answers with `fallback: true`; both down -> 502.
9. Only metrics clients read the metrics; the rest get 403 and an `access_denied` audit.

Pruebas unitarias nuevas:

- `test_pii.py`: cada tipo; tarjeta que no pasa Luhn no se toca; `EMP-0001` no es PII; tipos
  ordenados y sin repetir.
- `test_guard.py`: mensajes `assistant` no bloquean; pregunta normal no bloquea.
- `test_supervisor.py`: precedencia de reglas; JSON inválido y modelo caído -> `model_invalid`.
- `test_policies.py`: tema inexistente devuelve la lista de temas; acentos y mayúsculas.
- `test_cache.py`: TTL vencido con reloj fijo; tope de entradas saca la más vieja; 20 hilos.
- `test_resilience.py`: reintenta en 429 y 5xx con esperas 0.5 y 1.0 (sleep falso); no
  reintenta en 400; `CF_AIG_TOKEN` en el encabezado y fuera del error.
- `test_config.py` y `test_compliance.py`: cada variable nueva inválida; `METRICS_CLIENTS` vacía
  o con un cliente fantasma en producción.
- `test_api.py`: `/ready` 200 y 503; `/dashboard` sin clave y sin datos; `/metrics` con las
  secciones nuevas.

Punta a punta (`qa-e2e`, máximo 6 en total, por `data-testid` y con `expect`): las 5 actuales
compactadas a 3, más: el tablero muestra sus indicadores después de escribir la clave; una
pregunta con un correo no lo muestra en el último `assistant-answer`; una pregunta de vacaciones
muestra «12 días hábiles».

Verificaciones: `unit`, `contract` (01 a 05), `qa`, `e2e`, `evaluate` (incluye caché apagada
contra encendida) y `load` (60 peticiones, 10 hilos, todas 200).

## Riesgos

| Riesgo | Cómo se evita |
| --- | --- |
| Dos agentes editan `pipeline.py` o `main.py` a la vez. | Cadena secuencial developer -> security -> costs -> observability; solo `deploy` y `qa-e2e` en paralelo. |
| Las pruebas viejas cambian de resultado (EMP-9999, «Hola» con clasificación). | `qa-unit` las ajusta en la fase 0 y lo dice en su resumen; los contratos 01 a 04 no dependen de eso (EMP-9999 solo pide 200). |
| El supervisor encarece cada pregunta. | Reglas primero (sin modelo); el modelo pequeño solo cuando ninguna aplica, sin historial; ADR 0013. |
| La PII llega a la traza por la entrada del guardián o del run raíz. | El run raíz y `agent.guard` no reciben texto (solo tipos y conteos); los agentes siguientes reciben texto ya redactado. |
| Falsos positivos del guardián («actúa como enlace...»). | Lista corta y explícita; el 400 es claro; se revisa con el contador `blocked_inputs`. |
| Un patrón de PII se come parte de otro (tarjeta vs teléfono, CURP vs RFC). | Orden fijo, límites de dígito y Luhn; pruebas por tipo y mezcladas. |
| El revisor bloquea respuestas válidas que citan un id pedido que no existe. | Lo pide la spec; el mensaje invita a reintentar y queda `output_blocked` en audit y métricas. |
| La caché sirve datos a otro cliente o datos viejos. | Datos de solo lectura e iguales para todos; TTL de 300 s; nunca con historial ni PII; ADR 0015. |
| Condiciones de carrera en caché y contadores con 10 hilos. | Un candado por estructura; prueba con hilos y `verification load`. |
| Reintentos lentos en pruebas o en carga. | `sleep` inyectado por el reloj; el simulado caído no reintenta; tope `MODEL_RETRIES`. |
| El respaldo esconde una caída larga del modelo. | Contador `fallbacks` en `/metrics` y en el tablero; `fallback` en `agent_run`. |
| `CF_AIG_TOKEN` se filtra en un error de arranque o en un `repr`. | `repr=False`, errores sin valores, `from None`; contrato que busca el valor en `stderr`. |
| `/metrics` abierto en producción. | Compliance exige `METRICS_CLIENTS` con clientes reales; 403 y `access_denied` para el resto. |
| El tablero filtra datos o la clave. | HTML estático sin datos, `sessionStorage`, `textContent`; contrato que busca la clave en el HTML. |
| `load_test.py` contra Render choca con `RATE_LIMIT_PER_MINUTE` (30) y gasta cuota. | Solo falla con `5xx`; reporta los 429; `doc/operations.md` explica usar un cliente dedicado o un límite temporal. |
| Con varios workers la caché y las métricas se parten. | Un solo worker (ADR 0005); documentado en `doc/operations.md`. |
| `healthCheckPath: /ready` deja fuera de servicio un despliegue sin datos. | Es lo buscado: Render no envía tráfico a una instancia sin directorio, políticas o precios. |
| `data/policies.json` se desvía de la spec. | Copia exacta; el contrato compara ambos archivos. |
