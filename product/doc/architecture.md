# Arquitectura del HR Assistant (sesión 1)

El HR Assistant responde preguntas del personal de RH sobre empleados. Es una API FastAPI sin
estado con una página web, un solo agente con bucle con tope y un modelo detrás de una interfaz.

## Componentes

```mermaid
flowchart LR
    subgraph Navegador
        UI["index.html<br/>historial local"]
    end
    subgraph API["FastAPI (main.py, sin estado)"]
        ASK["POST /ask"]
        HEALTH["GET /health"]
        HOME["GET /"]
    end
    CFG["config.py<br/>Settings.from_env"]
    AGENT["agent.py<br/>bucle con tope"]
    LLM["llm.py<br/>LanguageModel.complete"]
    FAKE["FakeModel<br/>MODEL_PROVIDER=fake"]
    DIR["directory.py<br/>solo lectura"]
    DATA[("data/employees.json")]

    UI -- "question + history" --> ASK
    ASK -- "answer, steps, tools_used, tokens" --> UI
    HOME --> UI
    CFG -. "create_app inyecta" .-> API
    ASK --> AGENT
    AGENT -- "messages" --> LLM
    LLM --> FAKE
    AGENT -- "get_employee / search_by_department" --> DIR
    DIR --> DATA
```

## Secuencia de una pregunta

```mermaid
sequenceDiagram
    participant W as Página web
    participant A as POST /ask
    participant G as Agent
    participant M as LanguageModel
    participant D as EmployeeDirectory
    W->>A: question + history
    A->>A: valida (422 si vacía o larga)
    A->>G: run(history + question)
    loop hasta AGENT_MAX_STEPS
        G->>M: complete(messages)
        alt pide herramienta
            M-->>G: {"tool", "args"}
            G->>D: herramienta(args)
            D-->>G: resultado
            G->>G: agrega "Resultado de la herramienta: ..."
        else responde
            M-->>G: {"answer"}
        end
    end
    G-->>A: answer, steps, tools_used, tokens
    A-->>W: JSON
    W->>W: pinta con textContent y guarda historial
```

## Decisiones

- [0001 API sin estado con historial en el cliente](adr/0001-stateless-api.md)
- [0002 Modelo detrás de una interfaz e inyección de dependencias](adr/0002-model-interface-and-injection.md)
- [0003 Un solo agente con bucle con tope y protocolo JSON](adr/0003-bounded-agent-loop.md)

## Configuración

| Variable | Por omisión | Validación |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Solo `fake` |
| `AGENT_MAX_STEPS` | `3` | Entero mayor que 0 |
| `MAX_QUESTION_CHARS` | `2000` | Entero mayor que 0 |
| `EMPLOYEES_PATH` | `data/employees.json` | Relativo a `product/`; el archivo debe existir |

Un valor inválido impide arrancar con un `ConfigError` claro.
