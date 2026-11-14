# Reporte de la fábrica: HR Assistant, sesión 3 (costos)

**Estado:** LISTA

**Correcciones:** 1 de 2.

**Vueltas de QA:** 1 de 2. La revisión contra `QA.md` salió APROBADO en la primera vuelta.

**Pipeline:** [output/pipeline.md](pipeline.md) tiene 15 pasos. En el diagrama, `costs` (514 s) y `qa-e2e`
(101 s) salen de la misma verificación roja y se juntan en la siguiente, es decir, trabajaron en
paralelo.

## Tabla de `evaluate`

| Configuración | Calidad | Costo (USD) | Tokens de entrada |
| --- | --- | --- | --- |
| Línea base (sin palancas) | 100 % | 0.000918 | 1681 |
| Con palancas | 100 % | 0.000123 | 1111 |

Con las palancas el costo baja unas 7.5 veces y la calidad no cambia.
- **Línea base:** todas las preguntas van al modelo grande (`llama-3.3-70b`) con 10 mensajes de
  historial.
- **Con palancas:** las preguntas simples van al modelo pequeño (`llama-3.1-8b`) con 6 mensajes de
  historial.

Salvedad: con el modelo simulado la calidad no puede cambiar, porque el simulado solo mira el
último mensaje. Esta evaluación demuestra el ahorro de costo; la calidad con palancas solo se puede
medir con el gateway real.

## Bitácora

0. **Preparación.** `product/app/` existe, porque se trabaja de forma incremental sobre las
   sesiones 1 y 2. La bitácora `output/activity.jsonl` quedó vacía para esta corrida.
1. **Plan.** El arquitecto reescribió `output/plan.md`, agregó los ADR 0007, 0008 y 0009 y
   actualizó `product/doc/architecture.md`.
2. **Aprobación humana.** La persona aprobó el plan en el primer intento (0 rechazos).
3. **Pruebas primero.** `qa-unit` agregó 25 pruebas: 7 escenarios Gherkin y 18 pruebas unitarias.
   `verification unit` terminó con código 2 porque aún no existían `app.costs`, `app.gateway` ni
   `app.levers`. Rojo, como se esperaba.
4. **Especialistas en paralelo.** Se lanzaron en un solo mensaje.
   - `costs` creó `levers.py`, `costs.py`, `gateway.py` y `completion.py`. Este último no venía en
     el plan: evita un import circular entre `llm` y `gateway`.
   - `costs` también modificó `llm.py`, `agent.py`, `config.py`, `metrics.py` y `main.py`, y agregó
     `product/.env.example` (sin secretos), `product/data/model_prices.json` y el README
     actualizado.
   - `qa-e2e` escribió 3 pruebas de Playwright en `product/e2e/test_ask_page.py`.
5. **Unión y compuertas.**
   - Primera corrida: unit OK (75 pruebas) y contract OK (16 pruebas). QA falló con pylint en
     9.99/10, por 2 avisos C1803 en `tests/test_agent.py` y `tests/test_levers.py`.
   - Corrección 1. El supervisor se desvió de `/factory`, que pide relanzar a `costs` ante
     cualquier fallo que no sea de e2e. Los avisos estaban en archivos de prueba, que `costs` no
     puede editar, así que la corrección fue a `qa-unit`, su autor. Cambió dos aserciones sin
     desactivar avisos y sin cambiar lo que comprueban.
   - Segunda corrida, todas OK:
     - unit: 75 de 75 pruebas, 97.07 % de cobertura;
     - contract: 16 de 16 pruebas;
     - qa: 10.00/10;
     - e2e: 3 de 3 pruebas;
     - evaluate: tabla de arriba.
6. **Evaluador-optimizador.** `qa-style` escribió `output/qa-review.md` con **APROBADO** en la
   primera línea. Dejó tres mejoras opcionales que no bloquean:
   - `TOOL_RESULT_PREFIX` está repetido en `agent.py` y en `llm.py`;
   - `llm._fold` duplica `directory.normalize`;
   - el README no dice que hay que instalar el navegador de Playwright para correr `e2e`.
7. **Pipeline y reporte.** `scripts/pipeline.py` generó `output/pipeline.md` con 15 pasos.

## Observaciones

- **Prueba e2e débil.** La página no tiene un `data-testid` propio para cada respuesta, así que la
  primera prueba e2e no puede comprobar el texto de la respuesta: lo deduce de que aparece el
  `request-id` y no sale error. Para mejorarla, `developer` tendría que agregar ese `data-testid` a
  la página.
- **Aviso de pytest en e2e.** El fixture `base_url` es de sesión y está definido como método de
  instancia, algo que pytest marca como obsoleto. No afecta el resultado.

## Cómo probarlo

Con el modelo simulado, que no usa red ni cuesta:

```
cd product
uv run uvicorn app.main:app
```

Abre http://127.0.0.1:8000. Cada respuesta de `/ask` trae `model`, `route` y `cost_usd`, y
http://127.0.0.1:8000/metrics muestra el costo acumulado.

Con el modelo real: copia `product/.env.example` a `product/.env`, escribe ahí tu Account ID y tu
token de Cloudflare (nunca en el chat ni en el código) y corre
`uv run --env-file .env uvicorn app.main:app`.
