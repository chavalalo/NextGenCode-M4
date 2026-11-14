# Arquitectura del HR Assistant (sesiones 1 y 2)

El HR Assistant responde preguntas del personal de RH sobre empleados. Es una API FastAPI sin
estado con una página web, un solo agente con bucle con tope y un modelo detrás de una
interfaz. La sesión 2 agrega observabilidad: un id por petición, log JSON, métricas por
proceso y trazas opcionales en LangSmith.

## Componentes

```mermaid
flowchart LR
    subgraph Navegador
        UI["index.html<br/>historial local<br/>muestra request_id"]
    end
    subgraph API["FastAPI (main.py, sin estado de negocio)"]
        MW["middleware<br/>X-Request-ID, latencia, 500"]
        ASK["POST /ask"]
        HEALTH["GET /health"]
        METRICS["GET /metrics"]
        HOME["GET /"]
    end
    CFG["config.py<br/>Settings.from_env"]
    CLOCK["clock.py<br/>Clock inyectado"]
    LOG["logs.py<br/>JsonLogger"]
    MET["metrics.py<br/>Metrics por proceso"]
    TR["tracing.py<br/>Tracer"]
    AGENT["agent.py<br/>bucle con tope"]
    LLM["llm.py<br/>LanguageModel.complete"]
    DIR["directory.py<br/>solo lectura"]
    DATA[("data/employees.json")]
    STDOUT[["stdout<br/>una línea JSON por evento"]]
    LS[("LangSmith<br/>opcional")]

    UI -- "question + history" --> MW
    MW --> ASK
    MW --> HEALTH
    MW --> METRICS
    MW --> HOME
    ASK -- "answer, tokens, request_id" --> UI
    CFG -. "create_app inyecta" .-> API
    CLOCK -.-> LOG
    CLOCK -.-> MW
    MW -- "request, error" --> LOG
    ASK -- "agent_run, audit" --> LOG
    LOG --> STDOUT
    MW -- "latencia, estado" --> MET
    ASK -- "tokens" --> MET
    METRICS --> MET
    ASK --> AGENT
    TR -. "envuelve run, complete, herramientas" .-> AGENT
    TR -. "solo con LANGSMITH_TRACING y clave" .-> LS
    AGENT -- "messages" --> LLM
    AGENT -- "get_employee / search_by_department" --> DIR
    DIR --> DATA
```

## Secuencia de una pregunta

```mermaid
sequenceDiagram
    participant W as Página web
    participant MW as Middleware
    participant A as POST /ask
    participant G as Agent
    participant M as LanguageModel
    participant D as EmployeeDirectory
    participant L as JsonLogger
    participant X as Metrics
    W->>MW: POST /ask (X-Request-ID opcional)
    MW->>MW: request_id (cliente válido o UUID), start = monotonic()
    MW->>A: petición
    A->>A: valida (422 si vacía o larga)
    A->>G: run(history + question) dentro de tracer.context(request_id)
    loop hasta AGENT_MAX_STEPS
        G->>M: complete(messages)
        alt pide herramienta
            M-->>G: {"tool", "args"}
            G->>D: herramienta(args)
            D-->>G: resultado
        else responde
            M-->>G: {"answer"}
        end
    end
    G-->>A: answer, steps, tools_used, tool_calls, tokens, stopped
    A->>L: audit por herramienta, agent_run (solo conteos)
    A->>X: tokens
    A-->>MW: JSON con request_id
    alt excepción
        MW->>L: error (error_type)
        MW-->>W: 500 internal error + request_id
    end
    MW->>L: request (method, path, status, latency_ms)
    MW->>X: latencia y estado
    MW-->>W: respuesta + encabezado X-Request-ID
    W->>W: pinta con textContent, muestra request_id
```

## Decisiones

- [0001 API sin estado con historial en el cliente](adr/0001-stateless-api.md)
- [0002 Modelo detrás de una interfaz e inyección de dependencias](adr/0002-model-interface-and-injection.md)
- [0003 Un solo agente con bucle con tope y protocolo JSON](adr/0003-bounded-agent-loop.md)
- [0004 Id por petición y log JSON sin datos personales](adr/0004-request-id-and-json-logs.md)
- [0005 Métricas en memoria por proceso](adr/0005-in-process-metrics.md)
- [0006 Trazas opcionales con LangSmith detrás de un Tracer](adr/0006-optional-langsmith-tracing.md)

## Configuración

| Variable | Por omisión | Validación |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Solo `fake` |
| `AGENT_MAX_STEPS` | `3` | Entero mayor que 0 |
| `MAX_QUESTION_CHARS` | `2000` | Entero mayor que 0 |
| `EMPLOYEES_PATH` | `data/employees.json` | Relativo a `product/`; el archivo debe existir |
| `SERVICE_NAME` | `hr-assistant` | Texto no vacío |
| `SLO_P95_MS` | `2000` | Entero mayor que 0 |
| `LANGSMITH_TRACING` | `false` | `true` o `false`; sin `LANGSMITH_API_KEY` no se traza |
| `HIDE_INPUTS` / `HIDE_OUTPUTS` | `true` | `true` o `false` |

`LANGSMITH_API_KEY` se lee del entorno solo para saber si existe; no se guarda en `Settings`
ni se escribe en el log. Un valor inválido impide arrancar con un `ConfigError` claro.
