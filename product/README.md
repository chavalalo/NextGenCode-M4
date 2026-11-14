# HR Assistant

Asistente que responde preguntas del personal de Recursos Humanos sobre empleados
(por id, como `EMP-0004`, o por departamento). Es una API FastAPI sin estado con una
página web: el historial de la conversación vive en el navegador y un solo agente, con
un bucle con tope, consulta un directorio de empleados de solo lectura.

Cada petición se puede rastrear: lleva un id (`X-Request-ID`), deja líneas JSON en la
salida estándar y se cuenta en `GET /metrics`. Opcionalmente, las corridas del agente
quedan como trazas en LangSmith.

Cada respuesta dice qué modelo la contestó y cuánto costó. Por omisión el modelo es
simulado (sin red y sin gastar cuota); con `MODEL_PROVIDER=gateway` usa Cloudflare
Workers AI a través de AI Gateway.

La arquitectura y las decisiones están en `doc/architecture.md` y `doc/adr/`.

## Cómo correrlo

Desde la carpeta `product/`:

```bash
uv pip install -r requirements.txt
cp .env.example .env   # opcional: ajusta las variables
uv run uvicorn app.main:app --reload
```

Para el modelo real pon `MODEL_PROVIDER=gateway` y llena `CF_ACCOUNT_ID`,
`CF_GATEWAY_ID` y `CF_API_TOKEN` (sin las tres no arranca). El token es secreto: va
solo en `.env`, nunca en el repositorio, y no aparece en el log ni en los errores.

## Costo y palancas

El modelo real recibe
`POST https://gateway.ai.cloudflare.com/v1/{CF_ACCOUNT_ID}/{CF_GATEWAY_ID}/workers-ai/v1/chat/completions`
con `Authorization: Bearer {CF_API_TOKEN}`. Si falla, `POST /ask` responde `502` con
`{"detail": "model unavailable", "request_id": ...}`.

Cuatro palancas bajan el costo; cada una se mide con `verification evaluate`:

1. **Enrutamiento** (`ROUTING`, `ROUTER_MAX_CHARS`): una regla en código manda al
   modelo capaz (`MODEL_LARGE`) las preguntas largas o con «compara», «resume»,
   «explica», «por qué», «analiza» o «todos» (sin importar acentos ni mayúsculas); el
   resto va al barato (`MODEL_SMALL`). El motivo sale en `route`: `routing_off`,
   `long_question`, `keyword:<palabra>` o `simple`.
2. **Ventana de historial** (`HISTORY_WINDOW`): solo se mandan los últimos mensajes.
3. **Tope de salida** (`MODEL_MAX_TOKENS`) en cada llamada.
4. **Caché de AI Gateway** (`CACHE_TTL_SECONDS` > 0): manda `cf-aig-cache-ttl`; si el
   gateway responde `cf-aig-cache-status: HIT`, esa llamada cuenta en `cached_calls` y
   no cuesta.

El costo se calcula con `data/model_prices.json` (USD por millón de tokens), copia de
`spec/model_prices.json`, que viene de la página de precios de Workers AI. Los precios
cambian: para actualizarlos se edita `spec/model_prices.json` y se vuelve a copiar.
`MODEL_SMALL` y `MODEL_LARGE` deben tener precio o la aplicación no arranca. Con el
modelo simulado hay dos modelos con esos mismos nombres: responden igual, pero cada uno
se cobra con su precio, así que las palancas se miden sin red.

Abre `http://127.0.0.1:8000/`. Cada respuesta muestra su `Id de la petición`, que es
el dato que hay que pasar a soporte.

## Rutas

| Ruta | Para qué |
| --- | --- |
| `GET /` | Página web |
| `GET /health` | `{"status": "ok", "pid": ...}` |
| `POST /ask` | Recibe `{"question", "history"}` y responde `answer`, `steps`, `tools_used`, `input_tokens`, `output_tokens`, `request_id`, `model`, `route`, `cached_calls` y `cost_usd` |
| `GET /metrics` | `pid`, `requests`, `error_rate`, `latency_ms` (`p50`, `p95`), `tokens`, `slo` y `cost_usd` acumulado de este proceso |

Toda respuesta trae el encabezado `X-Request-ID`. Si el cliente lo manda y es válido
(letras, dígitos, `.`, `_` o `-`, hasta 128 caracteres) se conserva; si no, se genera
un UUID. Un error inesperado responde `500` con
`{"detail": "internal error", "request_id": ...}`.

## Log

Una línea JSON por evento en la salida estándar, con `ts` (UTC), `service`, `event` y
`request_id`. Eventos: `request`, `agent_run` (conteos, `model`, `route`,
`history_sent`, `cached_calls` y `cost_usd`; nunca el texto de la pregunta ni de la
respuesta), `audit` (una por herramienta llamada) y `error` (solo el tipo de error, por
ejemplo `ModelUnavailable`).

## Variables de entorno

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Modelo de lenguaje: `fake` (simulado) o `gateway` |
| `AGENT_MAX_STEPS` | `3` | Tope de vueltas del agente (entero mayor que 0) |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta (entero mayor que 0) |
| `EMPLOYEES_PATH` | `data/employees.json` | Archivo de empleados, relativo a `product/` |
| `SERVICE_NAME` | `hr-assistant` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en milisegundos (entero mayor que 0) |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas en LangSmith (`true` o `false`) |
| `LANGSMITH_API_KEY` | sin valor | Clave de LangSmith; sin ella no se traza ni se intenta conectar |
| `HIDE_INPUTS` / `HIDE_OUTPUTS` | `true` | No mandar a LangSmith el texto de preguntas ni respuestas |
| `CF_ACCOUNT_ID` | vacía | Cuenta de Cloudflare (obligatoria con `gateway`) |
| `CF_GATEWAY_ID` | `default` | Gateway de AI Gateway (obligatorio con `gateway`) |
| `CF_API_TOKEN` | vacía | Token de Cloudflare, secreto (obligatorio con `gateway`) |
| `MODEL_SMALL` | `@cf/meta/llama-3.1-8b-instruct-fast` | Modelo barato |
| `MODEL_LARGE` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Modelo capaz |
| `ROUTING` | `true` | Enrutamiento por pregunta (`true` o `false`) |
| `ROUTER_MAX_CHARS` | `80` | Preguntas más largas van al modelo capaz (entero mayor que 0) |
| `HISTORY_WINDOW` | `6` | Mensajes de historial que se mandan (entero, 0 o más) |
| `MODEL_MAX_TOKENS` | `300` | Tope de tokens de salida (entero mayor que 0) |
| `MODEL_TEMPERATURE` | `0` | Temperatura; con 0 las evaluaciones son repetibles |
| `CACHE_TTL_SECONDS` | `0` | Caché del gateway en segundos (0: apagada) |
| `PRICES_PATH` | `data/model_prices.json` | Precios por modelo, relativo a `product/` |

`.env.example` trae todas las variables sin valores secretos. Un valor inválido impide
arrancar con un `ConfigError`. La clave de LangSmith se lee del entorno y nunca se
guarda en la configuración ni se escribe en el log; el token de Cloudflare se guarda
pero no sale en `repr` ni en ningún mensaje.

## Pruebas

Desde la raíz del repositorio:

```bash
uv run python -m verification unit   # pruebas del producto, cobertura de 80 % o más
uv run python -m verification qa     # estilo de QA.md (pylint, 88 columnas, sin emojis)
uv run python -m verification contract  # contratos contra el producto corriendo
uv run python -m verification e2e       # Playwright sobre la página (modelo simulado)
uv run python -m verification evaluate  # costo y calidad: línea base contra palancas
```

Las pruebas usan un reloj fijo, el log en memoria y trazas apagadas: no usan red. El
modelo de gateway se prueba con un cliente `httpx` inyectado (`MockTransport`).
