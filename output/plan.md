# Plan del HR Assistant (sesión 3: costos)

Fuente: `spec/03-costs.md`, `spec/model_prices.json`, las especificaciones de las sesiones 1 y 2,
el contrato `verification/contract/test_contract_03.py`, `verification/evaluate.py`,
`verification/eval_set.json`, `verification/e2e.py` y el producto que ya existe en `product/`.
Todo lo de las sesiones 1 y 2 se conserva: los campos nuevos solo se agregan.

Reparto: `qa-unit` escribe las pruebas de `product/tests/`; `costs` escribe `product/app/`,
`product/data/`, `.env.example`, `README.md` y `requirements.txt`; `qa-e2e` escribe
`product/e2e/`. La página web no cambia.

## Módulos

| Archivo | Estado | Responsabilidad |
| --- | --- | --- |
| `app/levers.py` | nuevo | `choose_model(question, settings) -> Route(model, reason)` (palanca 1) y `trim_history(history, window)` (palanca 2). Funciones puras, sin red. |
| `app/costs.py` | nuevo | `PriceTable.load(path)`: precios en USD por millón; `price.cost(model, completions)` suma las llamadas no cacheadas; `KeyError` claro si el modelo no tiene precio. |
| `app/gateway.py` | nuevo | `GatewayModel(name, settings, http_client)`: llama a AI Gateway con `httpx`, manda `cf-aig-cache-ttl` si `CACHE_TTL_SECONDS > 0`, lee `usage` y `cf-aig-cache-status`. `ModelUnavailable` ante cualquier falla. Contiene el `SYSTEM_PROMPT` del protocolo JSON. |
| `app/llm.py` | cambia | `Completion` suma `cached: bool = False`. `FakeModel(departments, name)` con nombre. `build_models(settings, departments, http_client=None) -> dict[nombre, LanguageModel]` con `MODEL_SMALL` y `MODEL_LARGE` (fake o gateway). |
| `app/agent.py` | cambia | `run(messages, model=None)`: usa el modelo de esa pregunta para todas sus vueltas. `AgentResult` suma `completions` (lista de `Completion`) y `cached_calls`. No conoce precios ni HTTP. |
| `app/config.py` | cambia | Lee y valida las variables nuevas (tabla del spec). `gateway` exige los tres `CF_*`. `cf_api_token` con `field(repr=False)`; nunca en mensajes de error. |
| `app/metrics.py` | cambia | `add_cost(cost_usd)`; `snapshot` agrega `cost_usd` acumulado. |
| `app/main.py` | cambia | `create_app(..., models=None, prices=None, http_client=None)`. `/ask`: enruta, recorta historial, corre, calcula costo, responde con `model`, `route`, `cached_calls`, `cost_usd`; `ModelUnavailable` -> 502. |
| `app/clock.py`, `logs.py`, `tracing.py`, `directory.py` | igual | Reloj, log JSON, trazas y directorio de las sesiones 1 y 2. |
| `app/static/index.html` | igual | Ya tiene `data-testid` `question`, `send`, `answer` y `request-id`. |
| `data/model_prices.json` | nuevo | Copia exacta de `spec/model_prices.json`. |
| `.env.example` | nuevo | Todas las variables del producto; `CF_ACCOUNT_ID` y `CF_API_TOKEN` vacías. |
| `requirements.txt` | cambia | Agrega `httpx` explícito (ya lo trae el entorno de pruebas). Las dependencias de Playwright van en el `requirements.txt` raíz, no en el producto. |
| `README.md` | cambia | Modelo real, palancas, tabla de variables completa y cómo correr `e2e` y `evaluate`. |
| `e2e/test_ask_page.py` | nuevo (qa-e2e) | Tres pruebas de Playwright del spec. |

Reglas que fijan el contrato entre módulos:

- **Enrutador.** Se compara sobre la pregunta sin acentos y en minúsculas. Orden y motivos
  (`route`): `ROUTING=false` -> `routing_off`; `len(question) > ROUTER_MAX_CHARS` ->
  `long_question`; palabra clave al inicio de palabra (`\bcompara`, `\bresume`, `\bexplica`,
  `\bpor que`, `\banaliza`, `\btodos`) -> `keyword:<palabra>`; si no, `simple`. Así
  «Comparación» y «¿Por qué?» van al grande. Solo mira la pregunta, nunca el historial.
- **Ventana.** `trim_history(history, 0)` devuelve `[]` (cuidado: `history[-0:]` devuelve todo).
  Se aplica solo al historial del cliente, no a los mensajes que el agente agrega en sus vueltas.
  `HISTORY_WINDOW` es entero `>= 0`.
- **Costo.** `cost = sum((in * p_in + out * p_out) / 1_000_000)` sobre las llamadas con
  `cached=False`, con el precio del modelo **elegido por el enrutador**. Se redondea a 10
  decimales (no a 6: con el modelo simulado una respuesta cuesta del orden de 1e-6 y el contrato
  pide `> 0`). `input_tokens` y `output_tokens` siguen contando todas las llamadas.
- **Precios.** Al arrancar, `MODEL_SMALL` y `MODEL_LARGE` deben existir en `PRICES_PATH`; si no,
  `ConfigError`. `PRICES_PATH` relativo a `product/`, como `EMPLOYEES_PATH`.
- **Gateway.** URL
  `https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/workers-ai/v1/chat/completions`;
  cuerpo `{"model", "messages", "max_tokens", "temperature"}` con `SYSTEM_PROMPT` primero;
  texto en `choices[0].message.content`. Si el contenido viene entre cercas ```` ```json ```` se
  quitan; si no es un objeto JSON se devuelve como `{"answer": contenido}` para no gastar vueltas.
  Tiempo de espera fijo `GATEWAY_TIMEOUT_SECONDS = 30`. Error de red, estado no 2xx, JSON
  inválido o sin `usage` -> `ModelUnavailable` (sin el cuerpo ni el token en el mensaje).
- **Modelo simulado.** Dos `FakeModel` idénticos con nombres `MODEL_SMALL` y `MODEL_LARGE`;
  ignoran `max_tokens` y la caché (nunca `cached=True`).
- **Inyección.** Si las pruebas pasan un solo `model`, se usa para ambas rutas; el costo sale del
  nombre que eligió el enrutador. `http_client` se inyecta (en pruebas `httpx.MockTransport`).
- **Log.** `agent_run` suma `model`, `route`, `history_sent`, `cached_calls` y `cost_usd`; sigue
  sin texto de pregunta ni respuesta. El 502 emite `error` con `error_type="ModelUnavailable"`.
- **Configuración nueva**: `MODEL_PROVIDER` en `fake` o `gateway`; `MODEL_SMALL`, `MODEL_LARGE`
  no vacíos; `ROUTING` booleano; `ROUTER_MAX_CHARS`, `MODEL_MAX_TOKENS` enteros `> 0`;
  `HISTORY_WINDOW`, `CACHE_TTL_SECONDS` enteros `>= 0`; `MODEL_TEMPERATURE` decimal `>= 0`.

## Flujo de una pregunta

1. La página manda `POST /ask` con `{"question", "history"}` (sin cambios).
2. El middleware asigna `request_id` y toma el tiempo (sesión 2); FastAPI valida (422).
3. `choose_model` decide `model` y `route` con la pregunta.
4. `trim_history` deja los últimos `HISTORY_WINDOW` mensajes; se arma
   `messages = historial_recortado + [question]`.
5. `agent.run(messages, model=models[model])` dentro de `tracer.context(request_id)`.
6. En cada vuelta el modelo responde: el simulado con reglas; el de gateway hace el POST con
   `max_tokens`, `temperature` y, si aplica, `cf-aig-cache-ttl`, y marca `cached` si recibe
   `cf-aig-cache-status: HIT`.
7. Si el gateway falla, `ModelUnavailable` sube a `/ask`, que responde
   `502 {"detail": "model unavailable", "request_id"}` y registra `error`.
8. `prices.cost(model, result.completions)` da `cost_usd`; `cached_calls` cuenta los HIT.
9. `ask` escribe `audit` y `agent_run`, suma tokens y costo en `Metrics` y responde los campos de
   antes más `model`, `route`, `cached_calls`, `cost_usd`.
10. El middleware registra `request` y la latencia; `GET /metrics` incluye `cost_usd` acumulado.

## Pruebas

Unitarias y Gherkin con `create_app()` y dependencias inyectadas, sin red, cobertura de 80 % o
más. Las pruebas de las sesiones 1 y 2 siguen pasando; solo se agregan llaves esperadas
(`/ask` y `/metrics`).

Escenarios Gherkin nuevos (`product/tests/features/costs.feature`):

1. A short simple question goes to the small model and has a cost above zero.
2. A question with a keyword («Compara», «¿Por qué...?») goes to the large model with its reason.
3. A question longer than `ROUTER_MAX_CHARS` goes to the large model.
4. With routing turned off every question goes to the large model.
5. Only the last `HISTORY_WINDOW` history messages reach the model (modelo espía).
6. Metrics add up the cost of every answer.
7. When the gateway fails the API answers 502 `model unavailable` with the request id.
8. A gateway cache hit counts as a cached call and costs nothing.

Pruebas unitarias nuevas o ampliadas:

- `test_levers.py`: cada motivo de ruta; mayúsculas y acentos; borde `len == ROUTER_MAX_CHARS`
  (pequeño) y `+1` (grande); «resumen» y «comparación» activan; ventana 0, menor, igual y mayor
  que el historial.
- `test_costs.py`: costo con valores conocidos; llamadas cacheadas no cuestan; modelo sin precio
  lanza error; costo positivo con pocas palabras (sin redondear a cero).
- `test_gateway.py` (con `httpx.MockTransport`): URL, `Authorization: Bearer`, cuerpo con los
  cuatro campos y el prompt de sistema; `cf-aig-cache-ttl` solo con TTL > 0; lectura de `usage`;
  HIT -> `cached`; 500, tiempo agotado, JSON inválido y sin `usage` -> `ModelUnavailable`;
  cercas de código y texto libre.
- `test_config.py`: valores por omisión nuevos; `gateway` sin cada `CF_*` -> `ConfigError`;
  `repr(settings)` sin token; `HISTORY_WINDOW=-1`, `MODEL_TEMPERATURE=abc`, modelo sin precio ->
  `ConfigError`.
- `test_llm.py`: `build_models` con fake devuelve dos modelos con los nombres configurados.
- `test_agent.py`: `run(messages, model=...)` usa ese modelo en todas las vueltas;
  `completions` y `cached_calls`.
- `test_metrics.py`: `cost_usd` empieza en 0.0 y acumula.
- `test_api.py`: llaves exactas de `/ask` y `/metrics`; `agent_run` con `model`, `route` y
  `cost_usd` y sin texto de la pregunta; ni el token ni el id de cuenta aparecen en el log.

Pruebas de punta a punta (`product/e2e/`, máximo 6, por `data-testid` y con `expect`):

1. Asking a question shows the answer and its request id.
2. An empty question shows an error message in Spanish (dentro de `answer`).
3. A second question keeps the previous conversation on screen (usar `.last` o conteo, porque
   hay un `request-id` por respuesta).

Verificaciones: `unit`, `contract` (incluye `test_contract_03.py`), `qa`, `e2e` y `evaluate`.

## Riesgos

| Riesgo | Cómo se evita |
| --- | --- |
| Filtrar `CF_API_TOKEN` o `CF_ACCOUNT_ID` (repr, log, errores, `.env.example`). | `field(repr=False)`; `ModelUnavailable` sin URL ni cuerpo; log con `error_type`; `.env.example` con valores vacíos; prueba que busca el token en el log. |
| Llamadas a la red en pruebas o en `evaluate`. | `MODEL_PROVIDER=fake` por omisión; `http_client` inyectado; pruebas con `MockTransport`. |
| `cost_usd` redondeado a 0 con el modelo simulado y el contrato falla. | Redondeo a 10 decimales; prueba unitaria con pocas palabras. |
| Bajar la calidad al usar el modelo pequeño o recortar historial. | El enrutador manda al grande lo complejo; `evaluate` exige calidad igual o mejor y costo menor. Con el simulado la calidad no cambia porque solo mira el último mensaje. |
| `history[-0:]` manda todo el historial con `HISTORY_WINDOW=0`. | `trim_history` trata el 0 aparte; prueba de borde. |
| El enrutador falla por acentos o mayúsculas («Por qué», «COMPARA»). | Normalización sin acentos y en minúsculas, la misma de `directory.normalize`. |
| Falsos positivos por subcadena («todosantos»). | Coincidencia al inicio de palabra; se acepta «resumen» y «comparación» a propósito. |
| El modelo real no responde JSON y el agente gasta vueltas. | `SYSTEM_PROMPT` con el protocolo; se quitan cercas; texto libre se toma como respuesta. |
| Gateway lento bloquea hilos. | Tiempo de espera fijo y 502; el error cuenta en `error_rate`. |
| Respuesta cacheada contada como gasto o tokens perdidos. | `cached=True` solo con `HIT` exacto; los tokens se reportan, el costo no. |
| Precio desconocido para un modelo configurado. | Validación al arrancar con `ConfigError`. |
| Precios desactualizados (el JSON dice «verify before class»). | Copia de `spec/` sin cambios; el README indica de dónde vienen y cómo actualizarlos. |
| Romper contratos de sesiones 1 y 2 o la página. | Solo se agregan campos; `index.html` no cambia; se corren los tres contratos y `e2e`. |
| Una prueba e2e frágil (esperas o textos). | `data-testid`, `expect` de Playwright, nunca `time.sleep`. |
