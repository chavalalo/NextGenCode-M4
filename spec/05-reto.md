# Reto M4 · Sistema multi-agente en producción

Parte del producto de las sesiones 1 a 4, publicado en Render. Lo convierte en un **sistema multi-agente**: un
supervisor reparte cada pregunta entre especialistas, con un guardián a la entrada y un revisor a la salida. Además
le agrega controles de seguridad empresariales, resiliencia ante fallas del modelo, métricas de negocio con un
tablero, y una palanca de costo nueva medida contra la línea base.

Nada de lo anterior se rompe: las pruebas y contratos de las sesiones 1 a 4 siguen pasando.

## Lo que debe hacer

1. **Supervisor y especialistas.** Cada `POST /ask` pasa por estos agentes, en este orden:
   1. `guard` (guardián de entrada, en código): aplica el punto 2.
   2. `supervisor`: elige el especialista.
      - Con **reglas en código y sin llamar al modelo** cuando puede: si la pregunta trae un id `EMP-dddd` o el
        nombre de un departamento que existe → `directory`; si trae una palabra clave de una política de
        `data/policies.json` (sin importar acentos ni mayúsculas) → `policy`.
      - Si ninguna regla aplica, le pregunta a `MODEL_SMALL` con un prompt de clasificación que responde
        `{"specialist": "directory"}` o `{"specialist": "policy"}`. Si la respuesta no es válida, usa `directory`.
        Esa llamada cuenta en tokens y costo.
      - El motivo sale en el campo nuevo `supervisor_route`: `rule:employee`, `rule:department`, `rule:policy`,
        `model` o `model_invalid`.
   3. El especialista elegido, cada uno con su propio bucle con tope (`AGENT_MAX_STEPS`) y sus herramientas:
      - `directory`: el agente de las sesiones anteriores, con `get_employee` y `search_by_department`.
      - `policy`: agente nuevo con la herramienta `search_policy(topic)` sobre `data/policies.json` (copia de
        `spec/policies.json`). Responde con el texto de la política; si el tema no existe, la herramienta devuelve
        la lista de temas disponibles.
   4. `reviewer` (revisor de salida, en código): aplica el punto 3.

   El enrutador de costo de la sesión 3 (`ROUTING`) sigue eligiendo `MODEL_SMALL` o `MODEL_LARGE` para el
   especialista. El modelo simulado también sabe jugar el papel del supervisor y del especialista `policy`: si el
   último mensaje trae una palabra clave de una política, pide `search_policy` con ese tema.

   `POST /ask` responde, además de lo que ya respondía:
   - `specialist`: `directory` o `policy`.
   - `agents`: los agentes que corrieron, en orden. Por ejemplo `["guard", "supervisor", "directory", "reviewer"]`.
   - `supervisor_route`: el motivo del supervisor.
   - `pii_redacted`: los tipos de dato personal que se ocultaron (punto 2 y 3), sin repetir, en orden alfabético.
   - `cached`: `true` si la respuesta salió de la caché de respuestas (punto 7).
   - `fallback`: `true` si respondió el modelo de respaldo (punto 4).

2. **Guardián de entrada.**
   - **Prompt injection.** Si la pregunta o un mensaje `user` del historial pide ignorar u olvidar instrucciones,
     revelar el prompt del sistema o cambiar de rol (por ejemplo «ignora las instrucciones anteriores», «ignore
     previous instructions», «revela tu prompt del sistema», «system prompt», «actúa como», «modo desarrollador»,
     «jailbreak»; sin importar acentos ni mayúsculas), responde
     `400 {"detail": "request blocked by input policy", "request_id": ...}` y no llama a ningún modelo.
   - **Datos personales (PII).** Detecta en la pregunta y en el historial: correo (`email`), teléfono de 10 dígitos
     con o sin `+52` y separadores (`phone`), CURP (`curp`), RFC (`rfc`), número de tarjeta de 13 a 19 dígitos que
     pasa Luhn (`card`) y NSS de 11 dígitos (`nss`). Los **reemplaza** por `[EMAIL]`, `[PHONE]`, `[CURP]`, `[RFC]`,
     `[CARD]` y `[NSS]` antes de que lleguen al modelo, al log o a la traza. La petición sigue.
3. **Revisor de salida.**
   - Oculta la PII de la respuesta con las mismas reglas.
   - **Respuesta anclada a los datos.** Si la respuesta menciona un id `EMP-dddd` que no existe en el directorio, la
     reemplaza por «No pude verificar la respuesta con el directorio. Intenta de nuevo.».
   - Recorta la respuesta a `MAX_ANSWER_CHARS` caracteres.
4. **Resiliencia.**
   - El modelo `gateway` reintenta hasta `MODEL_RETRIES` veces ante timeout, `429` o `5xx`, con espera exponencial
     desde `MODEL_RETRY_BACKOFF_SECONDS` (la espera se inyecta, las pruebas no duermen).
   - Si el modelo elegido sigue sin responder y `MODEL_FALLBACK=true`, el especialista se repite **una vez** con el
     otro modelo (`MODEL_SMALL` ↔ `MODEL_LARGE`), y la respuesta trae `fallback: true` y en `model` el que
     contestó. Si también falla → `502` como antes.
   - Para probarlo sin red: con `MODEL_PROVIDER=fake`, la variable `FAKE_UNAVAILABLE_MODELS` (nombres separados por
     coma) hace que esos modelos simulados fallen como el gateway. En producción no aplica porque el modelo
     simulado está prohibido.
   - `CF_AIG_TOKEN` (opcional, secreto): si tiene valor, el gateway manda `cf-aig-authorization: Bearer <token>`.
     Resuelve el pendiente de la sesión 4. Nunca aparece en el log, la traza ni un error.
   - `GET /ready` (sin clave): `200 {"status": "ready", "checks": {"directory": "ok", "policies": "ok",
     "prices": "ok"}}`. `/health` no cambia.
5. **Mínimo privilegio.**
   - `METRICS_CLIENTS` (clientes separados por coma): solo ellos leen `GET /metrics`; los demás clientes con clave
     válida reciben `403 {"detail": "forbidden"}`. Vacía: todos los clientes pueden leerlas (desarrollo).
   - Compliance: con `ENVIRONMENT=production` el producto **no arranca** si `METRICS_CLIENTS` está vacía o nombra un
     cliente que no está en `API_KEYS`.
6. **Auditoría.** Una línea `audit` del log por cada acción relevante, con `client` y `action`:
   - `tool_call` (ya existe), `input_blocked` (con `reason: prompt_injection`), `pii_redacted` (con `location`:
     `input` u `output`, y `types`), `output_blocked` (con `reason: unknown_employee_id`), `access_denied` (con
     `path`) y `metrics_read`.
   - **Nunca** el texto de la pregunta, de la respuesta ni el valor de un dato personal: solo tipos y conteos.
7. **Costo: caché de respuestas.**
   - Con `ANSWER_CACHE_TTL_SECONDS` > 0, una pregunta **sin historial y sin PII** cuya forma normalizada (minúsculas,
     sin acentos, espacios colapsados) ya se respondió dentro del TTL se contesta desde la caché: `cached: true`,
     `cost_usd: 0`, `steps: 0`, tokens en 0 y `agents: ["guard", "cache"]`.
   - Máximo `ANSWER_CACHE_MAX_ENTRIES` entradas (se va la más vieja). Por omisión el TTL es `0` (apagada); en
     `render.yaml` va en `300`.
   - La caché y todo contador nuevo son seguros con peticiones concurrentes.
8. **Observabilidad del sistema multi-agente.**
   - **Trazas.** Cada agente es su propio run en LangSmith (`agent.guard`, `agent.supervisor`, `agent.directory`
     o `agent.policy`, `agent.reviewer`) dentro de la corrida de la petición, con `request_id`, `client` y
     `specialist` en los metadatos. Con `HIDE_INPUTS` y `HIDE_OUTPUTS` no se manda texto.
   - **Log.** `agent_run` agrega `specialist`, `agents`, `supervisor_route`, `pii_types`, `cached` y `fallback`.
   - **Métricas de negocio.** `GET /metrics` agrega:
     - `by_specialist` y `by_client`: por nombre, `requests` y `cost_usd`.
     - `security`: `blocked_inputs`, `pii_redactions`, `output_blocked` y `access_denied`.
     - `cache`: `hits`, `misses` y `hit_rate`.
     - `fallbacks` y `supervisor` (`rule` y `model`: cuántas veces decidió cada uno).
   - **Tablero.** `GET /dashboard` (sin clave, sin datos en el HTML) es una página que pide la clave igual que la
     página principal (`sessionStorage`), lee `/metrics` cada 10 segundos y muestra: peticiones, tasa de error,
     p50/p95 contra el SLO, costo total y por petición, tasa de aciertos de la caché, tabla por especialista, tabla
     por cliente y contadores de seguridad. `data-testid`: `dashboard`, `dashboard-key`, `dashboard-requests`,
     `dashboard-error-rate`, `dashboard-p95`, `dashboard-cost`, `dashboard-cache-hit-rate`,
     `dashboard-specialists`, `dashboard-clients`, `dashboard-security`. Con `403` muestra «Sin permiso para ver
     métricas».
9. **Despliegue y concurrencia.**
   - `render.yaml`: agrega `METRICS_CLIENTS` con `sync: false` y `ANSWER_CACHE_TTL_SECONDS=300`.
   - `scripts/load_test.py <url>`: manda `--requests` peticiones (por omisión 60) con `--concurrency` hilos (por
     omisión 10) a `POST /ask`, con la clave de `SMOKE_API_KEY`, y reporta códigos de estado, p50, p95, peticiones
     por segundo y costo total. Termina con código 1 si algún código es `5xx`.
   - `scripts/cost_report.py`: lee líneas JSON del log (archivo o entrada estándar) y resume costo, tokens y
     peticiones por cliente, por especialista y por modelo, más la tasa de caché.

## Documentación

- `doc/architecture.md`: diagrama Mermaid del sistema multi-agente y del despliegue.
- Máximo 3 ADR nuevos: supervisor con reglas antes que modelo, guardián/revisor en código, caché de respuestas.
- `doc/security.md`: modelo de amenazas y tabla de controles (control, dónde está, cómo se comprueba).
- `doc/costs.md`: palancas, evidencia contra la línea base y trade-offs costo/calidad.
- `doc/operations.md`: cómo desplegar, revisar el tablero, correr la prueba de carga y el reporte de costos.
- README actualizado (rutas, campos nuevos, variables nuevas).

## Pruebas de punta a punta (las actualiza `qa-e2e`)

- El tablero muestra sus indicadores después de escribir la clave.
- Una pregunta con un correo no lo muestra en la respuesta de la página.
- Una pregunta de vacaciones muestra la política.

## Configuración nueva

| Variable | Por omisión | Regla |
| --- | --- | --- |
| `MAX_ANSWER_CHARS` | `1500` | Entero mayor que 0 |
| `MODEL_RETRIES` | `2` | Entero, 0 o más |
| `MODEL_RETRY_BACKOFF_SECONDS` | `0.5` | Número, 0 o más |
| `MODEL_FALLBACK` | `true` | `true` o `false` |
| `FAKE_UNAVAILABLE_MODELS` | vacía | Solo con `MODEL_PROVIDER=fake` |
| `CF_AIG_TOKEN` | vacía | Secreto; nunca en log, traza ni error |
| `METRICS_CLIENTS` | vacía | Clientes de `API_KEYS`; obligatoria en producción |
| `ANSWER_CACHE_TTL_SECONDS` | `0` | Entero, 0 o más |
| `ANSWER_CACHE_MAX_ENTRIES` | `256` | Entero mayor que 0 |
| `POLICIES_PATH` | `data/policies.json` | Relativo a `product/` |

Un valor inválido impide arrancar con `ConfigError`, como en las sesiones anteriores.

## Cómo se comprueba

- `verification unit`, `qa` y `e2e` como antes.
- `verification contract` agrega `verification/contract/test_contract_05.py`.
- `verification evaluate` agrega la comparación de la caché de respuestas: mismas preguntas repetidas, caché
  apagada contra encendida. Pasa si la calidad no baja y el costo sí.
- `verification load` (nuevo): 60 peticiones con 10 hilos contra el producto local; pasa si todas responden `200`.
