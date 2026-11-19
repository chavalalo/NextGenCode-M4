CAMBIOS

Revisión de QA del producto después de las fases del reto (`spec/05-reto.md`, `output/plan.md`).
`uv run python -m verification qa` pasa (pylint 10.00/10): el estilo mecánico no se repite aquí.
La excepción acordada (código en inglés, comentarios y documentos en español) no se reporta.

## Hallazgos

### 1. Faltan `doc/security.md`, `doc/costs.md` y `doc/operations.md`

- Archivos: `product/doc/security.md`, `product/doc/costs.md`, `product/doc/operations.md` (no existen).
- Agente dueño: architect (fase 5 del plan).
- Qué incumple: QA.md, «Documentation»: "Document architectural decisions" e "Include setup and
  running instructions". `spec/05-reto.md` («Documentación») pide los tres documentos. Hoy no hay
  ningún lugar que explique cómo correr `scripts/load_test.py` y `scripts/cost_report.py`
  (el README no los menciona), ni el modelo de amenazas, ni la evidencia de costo contra la
  línea base.
- Qué hacer: crear los tres archivos como dice el plan: `security.md` con el modelo de amenazas
  y la tabla control / dónde está / cómo se comprueba; `costs.md` con las cinco palancas, la
  tabla de `verification evaluate` (caché apagada contra encendida) y los trade-offs;
  `operations.md` con el despliegue, el tablero, `load_test.py` (con `SMOKE_API_KEY`, aviso de
  los 429 por `RATE_LIMIT_PER_MINUTE`), `cost_report.py` y la salida de `verification load`.
  Enlazar `operations.md` desde la sección «Publicar en Render» del README.

### 2. El README no coincide con el código en el despliegue y en `.env.example`

- Archivos: `product/README.md` líneas 60-64 y 332; `product/.env.example` (sin `POLICIES_PATH`).
- Agente dueño: observability (versión final del README); developer para `.env.example`
  (`POLICIES_PATH` es variable suya).
- Qué incumple: QA.md, «README Maintenance Policy»: "Maintain up-to-date README" y "Changes to
  installation or setup procedures".
  - Líneas 60-64 dicen que en Render solo se escriben `API_KEYS`, `CF_ACCOUNT_ID` y
    `CF_API_TOKEN`. Pero `render.yaml` también pide `METRICS_CLIENTS` (`sync: false`), y sin esa
    variable el producto no arranca en producción (`app/compliance.py`,
    `_metrics_clients_violations`). Alguien que siga el README despliega un servicio que falla.
    Tampoco se mencionan `ANSWER_CACHE_TTL_SECONDS=300` ni `healthCheckPath: /ready`.
  - La línea 332 dice que «`.env.example` trae todas las variables», pero falta
    `POLICIES_PATH`.
- Qué hacer: en «Publicar en Render», agregar `METRICS_CLIENTS` a la lista de variables
  `sync: false` y explicar que debe nombrar clientes de `API_KEYS`. Mencionar
  `ANSWER_CACHE_TTL_SECONDS=300` y el health check en `/ready`. Agregar
  `POLICIES_PATH=data/policies.json` a `.env.example`, con su comentario.

### 3. El ADR 0014 ya no describe lo que hace el revisor

- Archivo: `product/doc/adr/0014-guard-and-reviewer-in-code.md` líneas 17-18.
- Agente dueño: architect.
- Qué incumple: QA.md, «Architecture Constraints»: "Follow established ADRs" y, en
  «Documentation», "Document architectural decisions". El ADR dice que el revisor reemplaza la
  respuesta si menciona cualquier `EMP-dddd` que no esté en el directorio. El código
  (`app/reviewer.py` líneas 55-73 y 92-94) y la adenda de `spec/05-reto.md` (punto 3) excluyen
  los ids que la persona escribió en su pregunta. El ADR documenta la versión que rompía la
  sesión 1.
- Qué hacer: actualizar la decisión («... que no está en el directorio **y que la persona no
  escribió en su pregunta**; se compara sin distinguir mayúsculas contra la pregunta ya
  redactada»). Agregar en «Consecuencias» que una persona que pregunta por un id inexistente
  recibe «no existe» y no el mensaje de verificación.

### 4. El log de auditoría `tool_call` guarda argumentos del modelo sin redactar

- Archivo: `product/app/pipeline.py` líneas 216-227 (`_audit_args`) y 759-767.
- Agente dueño: security.
- Qué incumple: QA.md, «Security»: "Follow security best practices". El punto 6 de la spec y el
  README (línea 246) prometen que el log nunca lleva el valor de un dato personal. Los `args` de
  `tool_call` los escribe el modelo y solo se recortan a 200 caracteres. Con el modelo real, el
  modelo puede copiar en un argumento (por ejemplo `department` o `topic`) un correo o teléfono
  que vio en la salida de `get_employee`, y ese valor llegaría al log tal cual. El guardián
  redacta lo que entra y el revisor lo que sale, pero nadie redacta este camino.
- Qué hacer: en `_audit_args`, pasar cada valor de texto por `app.pii.redact(...)` antes de
  recortarlo (`redact(value).text[:AUDIT_ARG_MAX_CHARS]`). Agregar una prueba unitaria con un
  modelo espía que pida una herramienta con un correo en los argumentos y compruebe que el log
  muestra `[EMAIL]` y no el valor (dueño de la prueba: qa-unit).

### 5. Reglas de negocio duplicadas en varios módulos

- Archivos y líneas:
  - El patrón de id de empleado `\bEMP-\d{4}\b` está tres veces: `product/app/supervisor.py:28`,
    `product/app/reviewer.py:15` y `product/app/llm.py:29`.
  - El plegado de acentos y mayúsculas está tres veces: `product/app/directory.py:9`
    (`normalize`), `product/app/llm.py:46` (`_fold`) y `product/app/cache.py:14`
    (`normalize_question`).
  - También se repiten `USER_ROLE` (`guard.py:15`, `pipeline.py:47`) y `TOOL_RESULT_PREFIX`
    (`agent.py:8`, `llm.py:25`).
- Agentes dueños: developer (`supervisor.py`, `llm.py`, `directory.py`); security
  (`reviewer.py`, `guard.py`); costs (`cache.py`).
- Qué incumple: QA.md, «Code Style»: "Keep functions small and focused", y «Architecture
  Constraints»: "Maintain existing architecture patterns" (cada regla en un solo módulo dueño).
  El supervisor decide `rule:employee` y el revisor decide qué es un id inventado con copias
  distintas de la misma regla. Si cambia el formato del id, una copia queda vieja y el
  supervisor y el revisor dejan de coincidir sin que falle ninguna prueba.
- Qué hacer:
  - Dejar `EMPLOYEE_ID_PATTERN` en `app/directory.py` (dueño del formato del id) e importarlo en
    `supervisor.py`, `reviewer.py` y `llm.py`.
  - Hacer que `llm._fold` use `directory.normalize`, y que `cache.normalize_question` sea
    `" ".join(normalize(question).split())`.
  - Importar `TOOL_RESULT_PREFIX` desde `app.agent` en `llm.py`, y `USER_ROLE` desde
    `app.guard` en `pipeline.py`.

## Revisado sin hallazgos

- Nombres en inglés y claros. Módulos con una responsabilidad: guardián, PII, revisor,
  supervisor, especialistas, caché, resiliencia, trazas y métricas separados. `pipeline.py`
  coordina sin lógica propia de cada agente.
- Docstrings Sphinx en lo público. Errores manejados: `InputBlocked` da 400,
  `ModelUnavailable` da 502 (solo el tipo en el log), `/ready` no deja salir el mensaje y los
  errores del gateway usan `from None`.
- Secretos: `cf_api_token`, `cf_aig_token` y `api_clients` con `repr=False`. Los mensajes de
  `ConfigError` no muestran valores secretos. `load_test.py` lee la clave solo del entorno y no
  la imprime.
- Trazas: el run raíz y los de guardián, supervisor y revisor no tienen entradas y su salida es
  un resumen. `agent_run` y los `audit` de bloqueo y PII solo llevan tipos y conteos.
- Configuración: las variables nuevas están en `config.py` con sus valores por omisión, sin
  valores fijos que debieran ser configuración.
