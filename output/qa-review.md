APROBADO

`uv run python -m verification qa` pasa (pylint 10.00/10, [OK] qa).

Revisión manual sin incumplimientos claros de QA.md:

- Nombres: claros y en inglés en todo `product/app` y `product/tests`.
- Funciones: pequeñas y con una sola responsabilidad; `create_app` delega en `_install_observability`,
  `_add_routes` y `_log_agent_run`.
- Configuración: los valores de operación (`SERVICE_NAME`, `SLO_P95_MS`, `LANGSMITH_TRACING`, `HIDE_*`,
  `AGENT_MAX_STEPS`, `MAX_QUESTION_CHARS`, `EMPLOYEES_PATH`) vienen del entorno y se validan con `ConfigError`.
  Las constantes que quedan en el código son de protocolo o tienen nombre propio.
- Docstrings: estilo Sphinx en clases y funciones públicas.
- Errores: el middleware convierte cualquier excepción en `500` con `request_id` y solo registra el tipo de
  error; el agente devuelve al modelo como texto el JSON inválido y los argumentos o herramientas malos.
- Hora: se inyecta con `Clock`; solo `SystemClock` usa `datetime.now`.
- README: explica qué es el producto, cómo instalarlo y correrlo, sus rutas, sus variables y cómo correr las
  pruebas.
- ADR 0001 a 0006: siguen vigentes con el código.
- Log: `agent_run` solo trae conteos, `error` solo el tipo de error y `audit` los argumentos recortados.
  La clave de LangSmith no se guarda en `Settings` ni se escribe en el log.

Mejoras opcionales que no bloquean la aprobación: el ADR 0006 habla de una "interfaz `Tracer`", pero en
`app/tracing.py` no hay un `Protocol` que la declare. Además, `TOOL_RESULT_PREFIX` está repetido en
`app/agent.py` y en `app/llm.py`.
