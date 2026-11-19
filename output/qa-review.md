APROBADO

`uv run python -m verification qa` pasa (pylint 10.00/10, [OK] qa).

Revisión manual de la sesión 4 (clave por cliente, límite, compliance, contenedor, CI y Render) sin
incumplimientos claros de QA.md:

- Nombres: claros y en inglés en `app/auth.py`, `app/ratelimit.py`, `app/compliance.py`, `app/errors.py`,
  `scripts/smoke.py` y en las pruebas nuevas (`security.feature`, `test_auth.py`, `test_ratelimit.py`,
  `test_compliance.py`, `test_security_api.py`).
- Funciones: pequeñas y con una sola responsabilidad. `parse_api_keys` delega en `_parse_entry` y `_malformed`;
  `compliance.violations` junta tres reglas puras; `RateLimiter.check` solo decide; `require_client` solo
  valida la clave y aplica el límite; `config._security_settings` agrupa lo nuevo.
- Configuración: `ENVIRONMENT`, `API_KEYS` y `RATE_LIMIT_PER_MINUTE` vienen del entorno y se validan con
  `ConfigError`. Lo que queda fijo (ventana de 60 s, mínimo de 16 caracteres, textos de 401 y 429) es regla de
  la spec y tiene nombre propio.
- Docstrings: estilo Sphinx en clases y funciones públicas, con `:raises:` donde aplica.
- Errores: `API_KEYS` mal formada falla con posición y largo, sin el valor y sin arrastrar la excepción
  (`from None`); compliance lanza `ConfigError` sin valores; `smoke.py` reporta solo el tipo de error de red.
- Hora y dependencias: `RateLimiter` usa el reloj inyectado; las pruebas lo avanzan a mano.
- Seguridad: claves comparadas con `hmac.compare_digest` contra todas; `ApiClient.key` y `api_clients` con
  `repr=False`; la página guarda la clave solo en `sessionStorage`; `.env.example` y `render.yaml` no traen
  secretos (`sync: false`); la clave de CI es de ejemplo y está marcada como tal.
- README: explica cómo correrlo local y con Docker, cómo publicar, la prueba de humo, las rutas con y sin
  clave, las variables nuevas y cada verificación.
- ADR: 0010, 0011 y 0012 describen lo que hace el código; 0001 a 0009 siguen vigentes (la API sigue sin
  estado de negocio; el límite en memoria es coherente con 0005). `doc/compliance-checklist.md` tiene la tabla
  de tres columnas.
- Log: `request`, `audit` y `agent_run` llevan `client`; `auth_rejected` solo `reason`; `rate_limited` solo
  `client` y `retry_after`; nunca la clave ni el texto de la pregunta.

Mejoras opcionales que no bloquean la aprobación: `pylint` y `pytest-playwright` se instalan aparte en
`ci.yml` en vez de estar fijados en `requirements.txt`; el servicio de `render.yaml` se llama `hr-assistant`
y debe ajustarse al nombre del repositorio que dé la persona al publicar.
