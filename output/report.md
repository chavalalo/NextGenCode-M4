# Reporte de la fábrica: HR Assistant

**Estado:** LISTA

**Correcciones:** 0 de 2 (el código pasó las dos verificaciones en el primer intento).

## Bitácora

1. **Plan.** El arquitecto escribió `output/plan.md`, tres ADR en `product/doc/adr/` y
   `product/doc/architecture.md`.
2. **Aprobación humana.** La persona aprobó el plan en el primer intento (0 rechazos).
3. **Pruebas primero (TDD).**
   - El agente de pruebas escribió 25 pruebas en `product/tests/`: 9 escenarios Gherkin y
     16 pruebas unitarias.
   - El primer intento de verificación terminó con código 127 porque `uv` no estaba instalado.
     Fue un fallo del entorno, no el rojo esperado.
   - La persona eligió instalar `uv`. Homebrew empezó a compilarlo desde el código fuente, junto
     con LLVM y Rust. Lo detuvimos a pedido de la persona y usamos el instalador oficial
     (`uv` 0.13.7 en `~/.local/bin`).
   - `verification unit` terminó con código 1: «todavía no existe product/app/». Rojo, como se
     esperaba.
4. **Código.** El desarrollador implementó `product/app/` (`config.py`, `directory.py`,
   `llm.py`, `agent.py`, `main.py` y `static/index.html`), además de `product/data/employees.json`
   y `product/requirements.txt`.
5. **Verificación.**
   - `verification unit`: OK. Pasaron 25 de 25 pruebas, con 97 % de cobertura (el mínimo es
     80 %).
   - `verification contract`: OK. Pasaron 9 de 9 pruebas.

## Observaciones

- El desarrollador tomó una decisión que el plan no fijaba: las herramientas desconocidas o que
  fallan no se agregan a `tools_used`. Ninguna prueba cubre este caso.
- Las pruebas muestran una advertencia de Starlette porque su `TestClient` con `httpx` está
  obsoleto. La advertencia viene de la librería, no del código del producto.

## Cómo abrir la página

```
cd product
uv run uvicorn app.main:app
```

Después abre http://127.0.0.1:8000
