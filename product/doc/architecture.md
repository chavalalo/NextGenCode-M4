# Arquitectura del HR Assistant (sesiones 1, 2 y 3)

El HR Assistant responde preguntas del personal de RH sobre empleados. Es una API FastAPI sin
estado con una página web, un solo agente con bucle con tope y un modelo detrás de una
interfaz. La sesión 2 agrega observabilidad (id por petición, log JSON, métricas, trazas
opcionales). La sesión 3 agrega el modelo real (Workers AI vía AI Gateway) y cuatro palancas de
costo: enrutamiento, ventana de historial, tope de salida y caché, con el costo de cada
respuesta.

## Componentes

```mermaid
flowchart LR
    subgraph Navegador
        UI["index.html<br/>historial local<br/>muestra request_id"]
    end
    subgraph API["FastAPI (main.py, sin estado de negocio)"]
        MW["middleware<br/>X-Request-ID, latencia, 500"]
        ASK["POST /ask<br/>502 si el modelo falla"]
        HEALTH["GET /health"]
        METRICS["GET /metrics"]
        HOME["GET /"]
    end
    CFG["config.py<br/>Settings.from_env"]
    LEV["levers.py<br/>choose_model, trim_history"]
    COST["costs.py<br/>PriceTable"]
    PRICES[("data/model_prices.json")]
    LOG["logs.py<br/>JsonLogger"]
    MET["metrics.py<br/>Metrics + cost_usd"]
    TR["tracing.py<br/>Tracer"]
    AGENT["agent.py<br/>bucle con tope"]
    LLM["llm.py<br/>LanguageModel, FakeModel x2"]
    GW["gateway.py<br/>GatewayModel (httpx)"]
    CF[("Cloudflare AI Gateway<br/>Workers AI, caché")]
    DIR["directory.py<br/>solo lectura"]
    DATA[("data/employees.json")]
    STDOUT[["stdout<br/>una línea JSON por evento"]]

    UI -- "question + history" --> MW
    MW --> ASK
    MW --> HEALTH
    MW --> METRICS
    MW --> HOME
    ASK -- "answer, model, route, cost_usd, request_id" --> UI
    CFG -. "create_app inyecta" .-> API
    ASK -- "pregunta" --> LEV
    ASK -- "modelo + completions" --> COST
    COST --> PRICES
    ASK -- "agent_run, audit" --> LOG
    MW -- "request, error" --> LOG
    LOG --> STDOUT
    ASK -- "tokens, costo" --> MET
    MW -- "latencia, estado" --> MET
    METRICS --> MET
    ASK -- "historial recortado + modelo elegido" --> AGENT
    TR -. "envuelve run, complete, herramientas" .-> AGENT
    AGENT -- "messages" --> LLM
    LLM -- "MODEL_PROVIDER=gateway" --> GW
    GW -- "max_tokens, temperature, cf-aig-cache-ttl" --> CF
    AGENT -- "get_employee / search_by_department" --> DIR
    DIR --> DATA
```

## Secuencia de una pregunta

```mermaid
sequenceDiagram
    participant W as Página web
    participant MW as Middleware
    participant A as POST /ask
    participant R as levers
    participant G as Agent
    participant M as Modelo elegido
    participant P as PriceTable
    participant X as Metrics
    W->>MW: POST /ask (X-Request-ID opcional)
    MW->>A: petición con request_id
    A->>R: choose_model(question)
    R-->>A: model, route
    A->>R: trim_history(history, HISTORY_WINDOW)
    A->>G: run(historial + question, model)
    loop hasta AGENT_MAX_STEPS
        G->>M: complete(messages)
        alt gateway falla
            M-->>A: ModelUnavailable
            A-->>W: 502 model unavailable + request_id
        else responde
            M-->>G: Completion (tokens, cached)
        end
    end
    G-->>A: answer, completions, cached_calls
    A->>P: cost(model, completions sin HIT)
    A->>X: tokens y cost_usd
    A-->>W: answer, model, route, cached_calls, cost_usd, request_id
```

## Decisiones

- [0001 API sin estado con historial en el cliente](adr/0001-stateless-api.md)
- [0002 Modelo detrás de una interfaz e inyección de dependencias](adr/0002-model-interface-and-injection.md)
- [0003 Un solo agente con bucle con tope y protocolo JSON](adr/0003-bounded-agent-loop.md)
- [0004 Id por petición y log JSON sin datos personales](adr/0004-request-id-and-json-logs.md)
- [0005 Métricas en memoria por proceso](adr/0005-in-process-metrics.md)
- [0006 Trazas opcionales con LangSmith detrás de un Tracer](adr/0006-optional-langsmith-tracing.md)
- [0007 Modelo real detrás de la interfaz, con cliente HTTP inyectado](adr/0007-gateway-model-behind-interface.md)
- [0008 Enrutamiento por regla y ventana de historial](adr/0008-rule-based-routing-and-history-window.md)
- [0009 Costo por respuesta y modelos simulados con precio](adr/0009-cost-per-answer-and-priced-fake-models.md)

## Configuración

| Variable | Por omisión | Validación |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | `fake` o `gateway` |
| `CF_ACCOUNT_ID`, `CF_GATEWAY_ID`, `CF_API_TOKEN` | vacía, `default`, vacía | Obligatorias y no vacías con `gateway`; el token no se muestra nunca |
| `MODEL_SMALL` | `@cf/meta/llama-3.1-8b-instruct-fast` | No vacío y con precio |
| `MODEL_LARGE` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | No vacío y con precio |
| `ROUTING` | `true` | `true` o `false` |
| `ROUTER_MAX_CHARS` | `80` | Entero mayor que 0 |
| `HISTORY_WINDOW` | `6` | Entero mayor o igual a 0 |
| `MODEL_MAX_TOKENS` | `300` | Entero mayor que 0 |
| `MODEL_TEMPERATURE` | `0` | Decimal mayor o igual a 0 |
| `CACHE_TTL_SECONDS` | `0` | Entero mayor o igual a 0 (0: sin caché) |
| `PRICES_PATH` | `data/model_prices.json` | Relativo a `product/`; el archivo debe existir |
| `AGENT_MAX_STEPS` | `3` | Entero mayor que 0 |
| `MAX_QUESTION_CHARS` | `2000` | Entero mayor que 0 |
| `EMPLOYEES_PATH` | `data/employees.json` | Relativo a `product/`; el archivo debe existir |
| `SERVICE_NAME` | `hr-assistant` | Texto no vacío |
| `SLO_P95_MS` | `2000` | Entero mayor que 0 |
| `LANGSMITH_TRACING` | `false` | `true` o `false`; sin `LANGSMITH_API_KEY` no se traza |
| `HIDE_INPUTS` / `HIDE_OUTPUTS` | `true` | `true` o `false` |

Los secretos (`CF_API_TOKEN`, `LANGSMITH_API_KEY`) nunca se escriben en el log ni en
`.env.example`. Un valor inválido impide arrancar con un `ConfigError` claro.
