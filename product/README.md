# HR Assistant

Asistente que responde preguntas del personal de Recursos Humanos sobre empleados
(por id, como `EMP-0004`, o por departamento). Es una API FastAPI sin estado con una
página web: el historial de la conversación vive en el navegador y un solo agente, con
un bucle con tope, consulta un directorio de empleados de solo lectura.

Cada petición se puede rastrear: lleva un id (`X-Request-ID`), deja líneas JSON en la
salida estándar y se cuenta en `GET /metrics`. Opcionalmente, las corridas del agente
quedan como trazas en LangSmith.

La arquitectura y las decisiones están en `doc/architecture.md` y `doc/adr/`.

## Cómo correrlo

Desde la carpeta `product/`:

```bash
uv pip install -r requirements.txt
uv run uvicorn app.main:app --reload
```

Abre `http://127.0.0.1:8000/`. Cada respuesta muestra su `Id de la petición`, que es
el dato que hay que pasar a soporte.

## Rutas

| Ruta | Para qué |
| --- | --- |
| `GET /` | Página web |
| `GET /health` | `{"status": "ok", "pid": ...}` |
| `POST /ask` | Recibe `{"question", "history"}` y responde `answer`, `steps`, `tools_used`, `input_tokens`, `output_tokens` y `request_id` |
| `GET /metrics` | `pid`, `requests`, `error_rate`, `latency_ms` (`p50`, `p95`), `tokens` y `slo` de este proceso |

Toda respuesta trae el encabezado `X-Request-ID`. Si el cliente lo manda y es válido
(letras, dígitos, `.`, `_` o `-`, hasta 128 caracteres) se conserva; si no, se genera
un UUID. Un error inesperado responde `500` con
`{"detail": "internal error", "request_id": ...}`.

## Log

Una línea JSON por evento en la salida estándar, con `ts` (UTC), `service`, `event` y
`request_id`. Eventos: `request`, `agent_run` (solo conteos, nunca el texto de la
pregunta ni de la respuesta), `audit` (una por herramienta llamada) y `error` (solo el
tipo de error).

## Variables de entorno

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Modelo de lenguaje (solo `fake`) |
| `AGENT_MAX_STEPS` | `3` | Tope de vueltas del agente (entero mayor que 0) |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta (entero mayor que 0) |
| `EMPLOYEES_PATH` | `data/employees.json` | Archivo de empleados, relativo a `product/` |
| `SERVICE_NAME` | `hr-assistant` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en milisegundos (entero mayor que 0) |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas en LangSmith (`true` o `false`) |
| `LANGSMITH_API_KEY` | sin valor | Clave de LangSmith; sin ella no se traza ni se intenta conectar |
| `HIDE_INPUTS` / `HIDE_OUTPUTS` | `true` | No mandar a LangSmith el texto de preguntas ni respuestas |

Un valor inválido impide arrancar con un `ConfigError`. La clave de LangSmith se lee
del entorno y nunca se guarda en la configuración ni se escribe en el log.

## Pruebas

Desde la raíz del repositorio:

```bash
uv run python -m verification unit   # pruebas del producto, cobertura de 80 % o más
uv run python -m verification qa     # estilo de QA.md (pylint, 88 columnas, sin emojis)
```

Las pruebas usan un reloj fijo, el log en memoria y trazas apagadas: no usan red.
