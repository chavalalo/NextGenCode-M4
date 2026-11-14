# Reporte de la fábrica: HR Assistant, sesión 2 (observabilidad)

**Estado:** LISTA

**Correcciones:** 1 de 2.

**Vueltas de QA:** 1 de 2. La revisión contra `QA.md` salió APROBADO en la primera vuelta.

**Pipeline:** el diagrama de la corrida está en [output/pipeline.md](pipeline.md) (12 pasos).

## Bitácora

0. **Preparación.** `product/app/` existe, porque se trabaja de forma incremental sobre el
   producto de la sesión 1. La bitácora `output/activity.jsonl` quedó vacía para esta corrida.
1. **Plan.** El arquitecto reescribió `output/plan.md`, agregó los ADR 0004, 0005 y 0006 y
   actualizó `product/doc/architecture.md`.
2. **Aprobación humana.** La persona aprobó el plan en el primer intento (0 rechazos).
3. **Pruebas primero.** El agente de pruebas agregó 25 pruebas: 9 escenarios Gherkin y 16 pruebas
   unitarias. `verification unit` terminó con código 2 porque aún no existían `app.clock`,
   `app.logs`, `app.metrics` ni `app.tracing`. Rojo, como se esperaba.
4. **Código.** El agente de observabilidad hizo estos cambios:
   - creó `clock.py`, `logs.py`, `metrics.py`, `tracing.py` y `product/README.md`;
   - modificó `config.py`, `agent.py`, `main.py`, `static/index.html` y
     `product/requirements.txt`.
5. **Encadenamiento con compuertas.**
   - Primera corrida: unit OK (50 pruebas) y contract OK (13 pruebas). QA falló con pylint en
     9.67/10, por 6 avisos `E1101 no-member` en `product/tests/test_tracing.py`.
   - Corrección 1. El orquestador se desvió de `/factory`, que pide relanzar al agente de
     observabilidad. Ese agente no puede editar pruebas, porque el hook de permisos se lo impide,
     así que la corrección fue al agente de pruebas, autor del archivo. Movió las listas del doble
     de LangSmith a una dataclass, sin desactivar avisos y sin cambiar lo que prueban las pruebas.
   - Segunda corrida: unit OK (50 de 50 pruebas, 97.93 % de cobertura), contract OK (13 de 13
     pruebas, sesiones 1 y 2) y qa OK (pylint 10.00/10).
6. **Evaluador-optimizador.** El agente de estilo escribió `output/qa-review.md` con
   **APROBADO** en la primera línea y sin hallazgos que bloqueen. Dejó dos mejoras opcionales:
   - el ADR 0006 menciona una interfaz `Tracer`, pero `tracing.py` no la declara como `Protocol`;
   - `TOOL_RESULT_PREFIX` está repetido en `agent.py` y en `llm.py`.
7. **Pipeline y reporte.** `scripts/pipeline.py` generó `output/pipeline.md` con 12 pasos.

## Cómo abrir la página, ver el log y las métricas

```
cd product
uv run uvicorn app.main:app
```

- Página: http://127.0.0.1:8000. Pregunta algo y copia el «Id de la petición» que muestra.
- Log: búscalo en la terminal donde corre el servidor. Cada línea JSON trae ese `request_id`.
- Métricas: http://127.0.0.1:8000/metrics
