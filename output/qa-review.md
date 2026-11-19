APROBADO

Revisión de QA, segunda y última vuelta. Comprobé los cinco hallazgos de la primera vuelta y
busqué incumplimientos graves nuevos. `uv run python -m verification qa` pasa (pylint
10.00/10). `uv run python -m verification evaluate` pasa y da las mismas cifras que
`doc/costs.md`. La excepción acordada del idioma (código en inglés; comentarios y documentos
en español) no se reporta.

## Hallazgos de la primera vuelta

1. **`doc/security.md`, `doc/costs.md` y `doc/operations.md`: corregido.** Existen los tres.
   `security.md` tiene el modelo de amenazas y la tabla de control, dónde vive y qué prueba lo
   comprueba, más los riesgos abiertos. `costs.md` tiene las palancas, la tabla de
   `verification evaluate` (baseline 0.000922, levers 0.000126, no_cache 0.000308 y cache
   0.000103, que coinciden con la salida real) y los trade-offs. `operations.md` cubre
   despliegue, variables, CI, `load_test.py` (con `SMOKE_API_KEY` y el aviso de los 429 por
   `RATE_LIMIT_PER_MINUTE`), `cost_report.py`, la salida de `verification load` y el tablero.
   El README los enlaza desde «Publicar en Render».
2. **README y `.env.example`: corregido.** «Publicar en Render» nombra `METRICS_CLIENTS`
   (`sync: false`, obligatoria, debe nombrar clientes de `API_KEYS`),
   `ANSWER_CACHE_TTL_SECONDS=300` y el health check en `/ready`, igual que `render.yaml`.
   `.env.example` trae `POLICIES_PATH=data/policies.json` con su comentario.
3. **ADR 0014: corregido.** La decisión excluye los ids que la persona escribió (se comparan
   sin mayúsculas contra la pregunta ya redactada). «Consecuencias» dice que un id inexistente
   que se preguntó recibe «no existe». Coincide con `app/reviewer.py`.
4. **Auditoría de `tool_call`: corregido.** `_audit_args` (`app/pipeline.py`, líneas 216-237)
   aplica `redact(value).text[:AUDIT_ARG_MAX_CHARS]`. `tests/test_audit_redaction.py` usa un
   modelo espía con un correo y un teléfono al principio del argumento. Comprueba que el log
   lleva `[EMAIL]` y `[PHONE]`, que el texto sale recortado y que los valores nunca aparecen.
5. **Reglas duplicadas: corregido.** `EMPLOYEE_ID_PATTERN` y `normalize` se definen solo en
   `app/directory.py`. `supervisor.py`, `reviewer.py`, `llm.py`, `guard.py` y `cache.py` los
   importan de ahí. `cache.normalize_question` usa `normalize`. `USER_ROLE` se define solo en
   `app/guard.py` (`pipeline.py` lo importa) y `TOOL_RESULT_PREFIX` solo en `app/agent.py`
   (`llm.py` lo importa).

## Coherencia de los documentos nuevos con el código

Revisé por muestreo los nombres de variables, archivos, pruebas y cifras:

- Las variables y valores de `render.yaml` coinciden con lo que dicen el README y
  `operations.md`.
- Los parámetros del script coinciden con `operations.md`: `--requests` 60,
  `--concurrency` 10, `SMOKE_API_KEY`, timeout de 90 s, código de salida 1 con 5xx y 2 sin
  clave.
- La prueba citada en `security.md` (`test_dashboard_is_public_and_carries_no_data_or_key`)
  existe.
- Las cifras de `costs.md` coinciden con `verification evaluate`.

No encontré contradicciones.

## Sin hallazgos nuevos

No hay incumplimientos graves nuevos de QA.md. El log de auditoría ya no tiene un camino sin
redactar, no hay secretos en el repositorio ni en el Blueprint y la documentación está al día.
