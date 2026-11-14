# Plan del HR Assistant (sesión 1)

Fuente: `spec/01-architecture.md`, `spec/employees.json`, `QA.md` y el contrato de
`verification/contract/test_contract.py`. No existía nada en `product/`.

## Módulos

| Archivo | Responsabilidad |
| --- | --- |
| `product/app/config.py` | `Settings` inmutable (dataclass `frozen`) construido con `Settings.from_env(environ)`; valida y lanza `ConfigError` con un mensaje claro si un valor es inválido. |
| `product/app/directory.py` | `EmployeeDirectory`: carga `employees.json` una vez, en solo lectura; expone `get_employee(employee_id)`, `search_by_department(department)` y `departments()`. |
| `product/app/llm.py` | Interfaz `LanguageModel` (`Protocol` con `complete(messages) -> Completion`), `Completion(text, input_tokens, output_tokens)`, `FakeModel` determinista y `build_model(settings, departments)` que elige proveedor. |
| `product/app/agent.py` | `Agent`: bucle con tope `max_steps`, interpreta el protocolo JSON, ejecuta las herramientas del directorio y devuelve `AgentResult(answer, steps, tools_used, input_tokens, output_tokens)`. |
| `product/app/main.py` | `create_app(settings, model, directory)` arma FastAPI con `GET /`, `GET /health` y `POST /ask`; al final del módulo `app = create_app()` lee el entorno. |
| `product/app/static/index.html` | Página única (HTML, CSS y JS en línea, sin librerías) que guarda el historial en el navegador y llama a `POST /ask`. |
| `product/app/__init__.py` | Marca el paquete (vacío). |
| `product/data/employees.json` | Copia exacta de `spec/employees.json`. |
| `product/requirements.txt` | fastapi, uvicorn, pydantic, httpx, pytest, pytest-bdd, pytest-cov. Nada más. |

Detalles que fijan el contrato entre módulos:

- `config.py`: `MODEL_PROVIDER` solo acepta `fake`; `AGENT_MAX_STEPS` y `MAX_QUESTION_CHARS` deben
  ser enteros mayores que 0; `EMPLOYEES_PATH` relativo se resuelve contra la carpeta `product/`
  (padre de `app/`), no contra el directorio actual, y el archivo debe existir.
- `directory.py`: los resultados de las herramientas son `str` en JSON con `ensure_ascii=False`
  (para que "Jorge Díaz" aparezca tal cual). Empleado inexistente: texto
  `No existe un empleado con id <id>.` (no excepción). Departamento sin empleados: lista vacía
  con un texto equivalente. La búsqueda de departamento ignora mayúsculas y acentos.
- `llm.py`: `FakeModel(departments)` recibe los departamentos por constructor; no importa
  `directory.py`. Tokens: entrada = palabras (`split()`) de todos los mensajes que recibe;
  salida = palabras de su respuesta.
- `agent.py`: herramientas registradas en un diccionario `nombre -> función`; no conoce FastAPI.
- Mensajes de la API y nombres de código en inglés; comentarios y docstrings en español, Sphinx.

## Flujo de una pregunta

1. La persona escribe en `data-testid="question"` y pulsa `data-testid="send"`.
2. El JS envía `POST /ask` con `{"question": ..., "history": [...]}`; `history` es el arreglo
   que guarda el navegador (pares `user` / `assistant` de vueltas anteriores).
3. FastAPI valida con Pydantic: `question` sin espacios no vacía y de largo máximo
   `settings.max_question_chars`; `history` opcional, roles solo `user` o `assistant`. Si falla,
   `422`.
4. `main.py` arma `messages = history + [{"role": "user", "content": question}]` y llama a
   `agent.run(messages)`. Nada se guarda en el servidor.
5. Vuelta `n` (n = 1..`max_steps`): el agente llama `model.complete(messages)`, suma tokens y
   cuenta `steps = n`.
6. Si la respuesta es `{"answer": ...}` termina con ese texto.
7. Si es `{"tool": ..., "args": {...}}`: ejecuta la herramienta, agrega `tool` a `tools_used`
   (en orden), agrega el pedido del modelo como mensaje `assistant` y el resultado como mensaje
   `user` que empieza con `Resultado de la herramienta: `, y pasa a la siguiente vuelta.
8. Si se agotan las vueltas sin `answer`, la respuesta es exactamente
   `No pude completar la respuesta. Intenta con una pregunta más concreta.`
9. La API responde `{"answer", "steps", "tools_used", "input_tokens", "output_tokens"}`.
10. El JS pinta la respuesta y las herramientas con `textContent`, agrega la pregunta y la
    respuesta al historial local; si la API falla muestra un mensaje en español.

Ejemplo verificado contra el contrato: "¿Quién es EMP-0004?" -> vuelta 1 pide `get_employee`,
vuelta 2 responde "Según el directorio: ..." -> `steps == 2`, `tools_used == ["get_employee"]`.
Con `AGENT_MAX_STEPS=1`: vuelta 1 pide la herramienta, se agota el tope -> `steps == 1` y el
mensaje de tope. (La herramienta pedida en la última vuelta sí se ejecuta y se registra.)

## Pruebas

Objetivo: 15 a 25 pruebas, cobertura de 80 % o más, todas con `create_app()` y dependencias
inyectadas (`TestClient`), sin red ni servidor.

Escenarios Gherkin (`product/tests/features/`):

1. `ask.feature` - Ask about an employee by id (EMP-0004 -> "Jorge Díaz", `get_employee`,
   2 steps).
2. Ask about a department (Finanzas -> "Sofía Gómez", `search_by_department`).
3. Ask about an unknown employee (EMP-9999 -> 200 y la respuesta dice que no existe).
4. Ask something unrelated (respuesta de ayuda, sin herramientas, 1 step).
5. The step cap stops the loop (`max_steps=1` -> mensaje exacto de tope, 1 step).
6. `validation.feature` - Empty question is rejected (422).
7. Too long question is rejected (`MAX_QUESTION_CHARS + 1` -> 422).
8. History sent by the client is accepted (200) y no se guarda entre peticiones.

Pruebas unitarias:

- `test_config.py`: valores por omisión; `AGENT_MAX_STEPS=0` lanza `ConfigError`; valor no
  numérico lanza `ConfigError`; `MODEL_PROVIDER` desconocido lanza `ConfigError`.
- `test_directory.py`: `get_employee` encuentra un id; id inexistente devuelve el texto de "no
  existe"; `search_by_department` ignora mayúsculas y acentos ("tecnologia").
- `test_llm.py`: cada una de las 4 reglas del `FakeModel`; conteo de tokens de entrada y salida.
- `test_agent.py`: suma de tokens entre vueltas; formato del mensaje
  `Resultado de la herramienta: `; JSON inválido o herramienta desconocida no rompen el bucle.
- `test_api.py`: `GET /health` devuelve `status` y `pid`; `GET /` contiene los tres
  `data-testid` y no usa `innerHTML`.

## Riesgos

| Riesgo | Cómo se evita |
| --- | --- |
| Acentos escapados (`Jorge Díaz`) y el contrato no encuentra el nombre. | `json.dumps(..., ensure_ascii=False)` en los resultados de herramientas. |
| Contar `steps` distinto al contrato. | `steps` = llamadas al modelo; documentado en ADR 0003 y probado con tope 1 y 3. |
| El servidor guarda estado (historial, caché por usuario) y deja de escalar. | Sin variables globales mutables; directorio de solo lectura; ADR 0001. |
| `EMPLOYEES_PATH` depende del directorio desde donde se arranca. | Resolver rutas relativas contra la carpeta `product/`. |
| Configuración inválida arranca a medias. | `Settings.from_env` valida todo al importar `main.py`; `ConfigError` con mensaje claro. |
| El modelo devuelve JSON inválido o pide una herramienta inexistente o con `args` malos. | El agente agrega un resultado de error (`Resultado de la herramienta: error ...`) y sigue; el tope garantiza que termina. |
| Inyección de HTML en la página a través de la respuesta. | Solo `textContent`; prueba que verifica que `index.html` no contiene `innerHTML`. |
| Historial manipulado por el cliente (roles falsos como `system`). | Pydantic con `Literal["user", "assistant"]` en `role`; 422 si no cumple. |
| Pregunta solo con espacios pasa como no vacía. | Validar tras `strip()`. |
| `llm.py` acoplado a `directory.py`. | `FakeModel` recibe la lista de departamentos por constructor; `main.py` cablea. |
| Dependencias fuera de lista o `pyproject.toml`. | `requirements.txt` limitado a las 7 librerías; sin `pyproject.toml`. |
| Uso de la hora del sistema. | No se necesita hora en esta sesión; si aparece, se inyecta un reloj. |
