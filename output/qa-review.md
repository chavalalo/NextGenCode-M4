APROBADO

`uv run python -m verification qa` pasa (pylint 10.00/10, [OK] qa).

Revisión manual de la sesión 3 (gateway, palancas y costos) sin incumplimientos claros de QA.md:

- Nombres: claros y en inglés en `app/gateway.py`, `app/levers.py`, `app/costs.py`, `app/completion.py` y en
  las pruebas nuevas (`test_gateway.py`, `test_levers.py`, `test_costs.py`, `costs.feature`).
- Funciones: pequeñas y con una sola responsabilidad. `choose_model` y `trim_history` son puras; `GatewayModel`
  separa `_headers`, `_body` y `_read_body`; `config.py` reparte la lectura en `_cloudflare_settings` y
  `_model_settings`; `main._answer` solo orquesta.
- Configuración: todas las variables de la spec (`CF_*`, `MODEL_SMALL`, `MODEL_LARGE`, `ROUTING`,
  `ROUTER_MAX_CHARS`, `HISTORY_WINDOW`, `MODEL_MAX_TOKENS`, `MODEL_TEMPERATURE`, `CACHE_TTL_SECONDS`,
  `PRICES_PATH`) vienen del entorno y se validan con `ConfigError`. Los precios viven en
  `data/model_prices.json`, no en el código. Lo que queda fijo (URL del gateway, encabezados de caché,
  tiempo de espera, palabras clave del enrutador) es protocolo o regla de la spec y tiene nombre propio.
- Docstrings: estilo Sphinx en clases y funciones públicas, con `:raises:` donde aplica.
- Errores: toda falla del gateway (red, no 2xx, JSON inválido, sin `usage`) se vuelve `ModelUnavailable` sin la
  URL ni el token, y `/ask` responde `502` con `request_id`. Un modelo sin precio o un `CF_*` faltante con
  `gateway` impide arrancar.
- Hora y dependencias: el cliente HTTP, los modelos, los precios, el reloj y el log se inyectan en
  `create_app`; las pruebas usan `httpx.MockTransport` y no salen a la red.
- README: explica cómo instalar, configurar (`.env.example`), correr el producto con modelo simulado o real,
  las rutas, las variables, las palancas y cómo correr cada verificación.
- ADR: 0007, 0008 y 0009 describen lo que hace el código; 0001 a 0006 siguen vigentes (la API sigue sin
  estado y el agente no conoce HTTP).
- Log: `agent_run` agrega solo `model`, `route`, `history_sent`, `cached_calls` y `cost_usd`; `error` solo el
  tipo. `CF_API_TOKEN` tiene `repr=False` y ningún mensaje de error lo incluye; `.env.example` no trae
  secretos.

Mejoras opcionales que no bloquean la aprobación: `TOOL_RESULT_PREFIX` sigue repetido en `app/agent.py` y
`app/llm.py` (y su texto también aparece en `SYSTEM_PROMPT` de `app/gateway.py`); `llm._fold` duplica
`directory.normalize`; el README no menciona que Playwright necesita instalar su navegador para
`verification e2e`.
