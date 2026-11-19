# Plan del HR Assistant (sesión 4: producción)

Fuente: `spec/04-production.md`, las especificaciones de las sesiones 1 a 3, el contrato
`verification/contract/test_contract_04.py` (y su `conftest.py`), `verification/server.py`,
`verification/e2e.py`, `verification/production.py`, `verification/qa.py`,
`scripts/publish.py` y el producto que ya existe en `product/`. Todo lo de las sesiones 1 a 3
se conserva: los contratos 01 a 03 ya mandan `X-API-Key` (la clave de la fábrica).

Reparto (según `hooks/permissions.py`):

- `qa-unit`: `product/tests/` (pruebas nuevas y fixtures con clave).
- `security`: `product/app/` (incluye `static/index.html`), `requirements.txt`, `README.md`,
  `.env.example` y `doc/compliance-checklist.md`.
- `deploy`: `Dockerfile`, `.dockerignore`, `.gitignore`, `render.yaml`,
  `.github/workflows/ci.yml` y `scripts/smoke.py`, todos dentro de `product/`. `product/` es la
  raíz del repositorio que crea `scripts/publish.py`: por eso el CI y el Blueprint van ahí.
- `qa-e2e`: `product/e2e/`.

## Módulos

| Archivo | Estado | Responsabilidad |
| --- | --- | --- |
| `app/auth.py` | nuevo | `parse_api_keys(raw) -> tuple[ApiClient]` (valida y nunca muestra valores) y `identify_client(header, clients) -> str or None` con `hmac.compare_digest` contra todas las claves. |
| `app/ratelimit.py` | nuevo | `RateLimiter(limit, clock, window=60)`: ventana deslizante por cliente con `clock.monotonic()` y candado; `check(client) -> Decision(allowed, retry_after)`. |
| `app/compliance.py` | nuevo | `violations(settings) -> list[str]` con las tres reglas de producción; `enforce(settings)` lanza `ConfigError` con los nombres de las reglas, sin valores. |
| `app/config.py` | cambia | Lee `ENVIRONMENT` (`development` o `production`), `API_KEYS` (con `auth.parse_api_keys`, campo `repr=False`) y `RATE_LIMIT_PER_MINUTE` (entero `> 0`). Guarda también `langsmith_tracing_requested`. |
| `app/main.py` | cambia | `create_app` llama `compliance.enforce`, arma `RateLimiter` con el reloj inyectado y agrega la dependencia `require_client` (401, luego 429) a `/ask` y `/metrics`. Pone `client` en `request`, `audit`, `agent_run` y en la traza. |
| `app/tracing.py` | cambia | `context(request_id, client=None)`: metadatos `{"request_id", "client"}`. Nunca la clave. |
| `app/static/index.html` | cambia | Campo `data-testid="api-key"` tipo `password`; guarda en `sessionStorage`; manda `X-API-Key`; 401 -> «Clave inválida»; 429 -> «Demasiadas preguntas; espera N segundos». |
| `app/agent.py`, `llm.py`, `gateway.py`, `levers.py`, `costs.py`, `metrics.py`, `logs.py`, `clock.py`, `directory.py` | igual | Lo de las sesiones 1 a 3. |
| `requirements.txt` | cambia | Agrega `pylint` y `pytest-playwright` para que el CI instale todo con un solo archivo. |
| `.env.example`, `README.md` | cambia | Variables nuevas (clave de ejemplo vacía), cómo correr con Docker y cómo publicar. |
| `doc/compliance-checklist.md` | nuevo (security) | Tabla: regla, dónde está en el código, cómo se comprueba (prueba unitaria o contrato). |
| `Dockerfile`, `.dockerignore`, `.gitignore` | nuevo (deploy) | Imagen `python:3.12-slim`, usuario no root, `sh -c "exec uvicorn ... --port ${PORT:-8000}"`; fuera `.env`, `tests/`, `e2e/`, cachés, `.coverage`, `.git`. |
| `.github/workflows/ci.yml` | nuevo (deploy) | `style` -> `unit` -> `e2e` -> `docker`, encadenados con `needs`, en `push` y `pull_request`, `permissions: contents: read`. |
| `render.yaml` | nuevo (deploy) | Un servicio web con el nombre del repositorio, `runtime: docker`, `plan: free`, `healthCheckPath: /health`, `autoDeployTrigger: checksPass`, variables fijas y secretos con `sync: false`. |
| `scripts/smoke.py` | nuevo (deploy) | `smoke.py <url>` con la clave en `SMOKE_API_KEY`; tres comprobaciones con `[OK]`/`[FAIL]`; código 0 si todas pasan. |
| `e2e/test_ask_page.py` | cambia (qa-e2e) | Escribe primero la clave de `E2E_API_KEY`; prueba nueva de clave equivocada. |

Reglas que fijan el contrato entre módulos:

- **`API_KEYS`.** Entradas separadas por `,`, cada una `cliente:clave` partida en el primer `:`;
  se quitan espacios a los lados. Vacía o solo espacios -> sin clientes (válido en desarrollo).
  Error (`ConfigError`) si una entrada está vacía, no tiene `:`, el cliente o la clave quedan
  vacíos, el cliente no cumple `[A-Za-z0-9._-]{1,64}`, o hay clientes o claves repetidos. El
  mensaje dice la posición (desde 1) y el largo: `API_KEYS entry 2 is malformed (length 27)`.
  Se lanza con `from None` para que la traza no arrastre la excepción original.
- **Autenticación.** Encabezado `X-API-Key`; ausente o sin coincidencia -> `401
  {"detail": "invalid or missing API key"}`. Se compara contra todas las claves sin salir antes
  (tiempo constante). Públicas: `GET /`, `GET /health`, `/docs` y `/openapi.json`.
- **Límite.** Va después de la clave (primero 401, luego 429), por cliente, en `/ask` y
  `/metrics`. Ventana deslizante de 60 s: si ya hay `RATE_LIMIT_PER_MINUTE` peticiones aceptadas
  en la ventana -> `429 {"detail": "rate limit exceeded"}` con `Retry-After =
  max(1, ceil(más_antigua + 60 - ahora))`. Las rechazadas no se cuentan. Memoria por proceso,
  acotada por número de clientes y límite.
- **Compliance** (solo con `ENVIRONMENT=production`): `MODEL_PROVIDER=fake`; sin clientes o
  alguna clave con menos de 16 caracteres; `LANGSMITH_TRACING=true` y `HIDE_INPUTS` o
  `HIDE_OUTPUTS` en `false` (se usa lo pedido, no solo si hay clave de LangSmith, para fallar
  antes). `create_app` la aplica, así que `import app.main` termina con código distinto de 0.
- **Log.** `request` lleva `client` (o `null` en rutas públicas y rechazos); `audit` y
  `agent_run` llevan `client`. Eventos nuevos: `auth_rejected` con `reason` (`missing` o
  `invalid`) y `rate_limited` con `client` y `retry_after`. Nunca la clave ni su prefijo.
- **Página.** Al cargar lee la clave de `sessionStorage`; al enviar la guarda ahí. Pregunta vacía
  sigue mostrando «Escribe una pregunta antes de enviar.» sin llamar a la API. Los mensajes de
  401 y 429 se muestran dentro de `data-testid="answer"`; N sale de `Retry-After`.
- **CI.** `style`: `pylint app tests scripts --max-line-length=88` con los mismos `--disable` de
  `verification/qa.py`. `unit`: `pytest tests --cov=app --cov-fail-under=80`. `e2e`:
  `python -m playwright install --with-deps chromium`, arranca uvicorn en segundo plano con
  `MODEL_PROVIDER=fake` y `API_KEYS=ci:<clave de ejemplo de 16+ caracteres>`, espera `/health` y
  corre `pytest e2e --base-url http://127.0.0.1:8000` con esa clave en `E2E_API_KEY`. `docker`:
  `docker build`. Acciones: `actions/checkout@v5`, `actions/setup-python@v6`, Python 3.12.
- **Render.** Variables fijas: `ENVIRONMENT=production`, `MODEL_PROVIDER=gateway`,
  `HIDE_INPUTS=true`, `HIDE_OUTPUTS=true`. Con `sync: false`: `API_KEYS`, `CF_ACCOUNT_ID`,
  `CF_API_TOKEN`. `LANGSMITH_API_KEY` no va en el Blueprint.

## Flujo de una pregunta

1. La persona escribe su clave en `api-key`; la página la guarda en `sessionStorage`.
2. La página manda `POST /ask` con `{"question", "history"}` y `X-API-Key`.
3. El middleware asigna `request_id` y toma el tiempo (sesión 2).
4. La dependencia `require_client` busca la clave: si falta o no coincide, emite `auth_rejected`
   y responde 401. Si coincide, pone `request.state.client`.
5. `RateLimiter.check(client)`: si se pasa del límite, emite `rate_limited` y responde 429 con
   `Retry-After`.
6. FastAPI valida el cuerpo (422).
7. Como en la sesión 3: enrutador, ventana de historial, `agent.run` dentro de
   `tracer.context(request_id, client)`, costo; 502 si el gateway falla.
8. `ask` escribe `audit` y `agent_run` con `client`, suma tokens y costo, y responde.
9. El middleware escribe `request` con `client`, `status` y latencia.
10. La página muestra la respuesta, «Clave inválida» (401) o «Demasiadas preguntas; espera N
    segundos» (429).

Arranque: `Settings.from_env` valida `API_KEYS` y lo demás -> `compliance.enforce` -> si algo
falla, `ConfigError` y el proceso no arranca.

## Pruebas

Unitarias y Gherkin con `create_app()` y dependencias inyectadas, sin red, cobertura de 80 % o
más. Primero, `qa-unit` actualiza `tests/conftest.py`: las fábricas de clientes ponen
`API_KEYS=tester:<clave de prueba de 16+ caracteres>` si la prueba no lo da, y el
`TestClient` manda `X-API-Key` por omisión. Así las pruebas de las sesiones 1 a 3 siguen
pasando sin tocar sus pasos.

Escenarios Gherkin nuevos (`product/tests/features/security.feature`):

1. Asking without an API key returns 401 with the exact message.
2. Asking with a wrong API key returns 401.
3. Health, the page and the docs need no key.
4. Metrics need a key.
5. The client name appears in the log and the key never does (busca la clave en todo el log).
6. A client over the limit gets 429 with Retry-After; after the clock advances 60 s it can ask
   again (reloj fijo).
7. Each client has its own limit (el cliente A agotado no frena al B).
8. Production refuses to start with the fake model / with a short key / with tracing that shows
   inputs (Scenario Outline).

Pruebas unitarias nuevas o ampliadas:

- `test_auth.py`: una y varias entradas; espacios; `:` dentro de la clave; vacía; sin `:`;
  cliente vacío; clave vacía; cliente con caracteres inválidos; repetidos; el mensaje de error
  no contiene la clave y sí la posición y el largo; `repr(settings)` sin claves;
  `identify_client` con clave buena, mala, vacía y `None`.
- `test_ratelimit.py`: el límite exacto pasa y el siguiente no; `Retry-After` entero `>= 1` y
  correcto con el reloj; ventana deslizante (avanzar 30 s y 31 s); las rechazadas no cuentan;
  clientes independientes.
- `test_compliance.py`: cada regla por separado; varias a la vez; clave de 15 y de 16
  caracteres; en `development` nada se exige; el mensaje no trae valores.
- `test_config.py`: `ENVIRONMENT` inválido, `RATE_LIMIT_PER_MINUTE` 0 o texto -> `ConfigError`;
  valores por omisión (`development`, sin clientes, 30).
- `test_tracing.py`: `context(request_id, client)` pone ambos en los metadatos.
- `test_api.py`: orden 401 antes de 429; `X-Request-ID` también en 401 y 429; `auth_rejected` y
  `rate_limited` sin clave; `/metrics` con clave cuenta las respuestas 401 y 429.

Pruebas de punta a punta (`product/e2e/`, máximo 6, por `data-testid` y con `expect`):

1. Las tres de la sesión 3, escribiendo antes la clave de `E2E_API_KEY` en `api-key` (si falta
   la variable, la prueba falla con un mensaje claro; la clave nunca va escrita en la prueba).
2. A wrong key shows «Clave inválida».
3. The key field is a password field and the key is kept in `sessionStorage`, not in
   `localStorage` (con `page.evaluate`).

Verificaciones: `unit`, `contract` (incluye `test_contract_04.py`), `qa`, `e2e`, `evaluate` y,
tras publicar, `production <url>`.

## Riesgos

| Riesgo | Cómo se evita |
| --- | --- |
| La clave se filtra en log, traza, error, `repr` o traceback. | Solo se registra `client`; `repr=False`; errores con posición y largo; `from None`; prueba que busca la clave en todo el log y en el `stderr` del arranque (contrato). |
| Comparación de claves vulnerable a tiempo. | `hmac.compare_digest` contra todas las claves, sin salida temprana. |
| Las pruebas de sesiones 1 a 3 pasan a 401 en bloque. | `conftest.py` pone clave y encabezado por omisión; la verificación ya los manda. |
| `API_KEYS` vacía deja la API cerrada en desarrollo sin aviso. | Es el comportamiento seguro por omisión; el README y `.env.example` lo explican. |
| El límite cuenta mal o deja pasar ráfagas. | Ventana deslizante con candado y reloj inyectado; pruebas de borde con `FixedClock`. |
| Límite por proceso: con varios workers se multiplica. | Un solo worker en el Dockerfile (como las métricas, ADR 0005); documentado. |
| Fuerza bruta de claves (el límite es por cliente y el anónimo no tiene cliente). | Claves de 16+ caracteres obligatorias en producción; evento `auth_rejected` para verlo. Límite por IP queda fuera del alcance. |
| Arrancar en producción con el simulado o con trazas que muestran datos. | `compliance.enforce` en `create_app`; contrato con `import app.main`. |
| `/docs` deja de cargar porque `/openapi.json` pide clave. | Solo `/ask` y `/metrics` llevan la dependencia. |
| La clave queda en `localStorage` o en el HTML. | `sessionStorage` y prueba e2e que lo comprueba; el HTML no trae valor. |
| Secretos en el repositorio (`.env`, `render.yaml`, CI). | `.gitignore` y `.dockerignore` con `.env`; `sync: false`; en el CI una clave de ejemplo; `publish.py` revisa `.gitignore`. |
| `${PORT}` no se expande en el `CMD` de Docker. | Forma `sh -c "exec uvicorn ..."`. |
| La imagen corre como root o lleva pruebas. | `useradd` y `USER`; `.dockerignore` deja fuera `tests/` y `e2e/`. |
| El CI difiere de la verificación local (pylint, rutas, navegador). | Mismo comando de pylint que `verification/qa.py`; `playwright install --with-deps chromium`; espera a `/health` antes de `e2e`. |
| Render publica un commit con el CI en rojo, o actualiza otro servicio. | `autoDeployTrigger: checksPass`; servicio con el nombre del repositorio. |
| El Blueprint pide un valor para `LANGSMITH_API_KEY`. | No se declara en `render.yaml`; se agrega en Render > Environment si hace falta. |
| El servicio gratuito duerme y la prueba de humo falla por tiempo. | `verification production` espera hasta 90 s; `smoke.py` igual. |
| La clave del humo queda en el historial de la terminal. | Se lee de `SMOKE_API_KEY`, nunca de un argumento. |
