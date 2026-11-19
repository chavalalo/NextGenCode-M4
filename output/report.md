# Reporte de la fábrica: HR Assistant, sesión 4 (producción)

**Estado:** LISTA

**URL pública:** https://hr-assistant-1q29.onrender.com

**Correcciones:** 1 de 2.

**Vueltas de QA:** 1 de 2. La revisión contra `QA.md` salió APROBADO en la primera vuelta.

**Ciclos de triage:** 1 de 2. El dueño fue `persona` (configuración, no código).

**Pipeline:** el diagrama de la corrida está en [output/pipeline.md](pipeline.md) (18 pasos). En el
diagrama, `security`, `deploy` y `qa-e2e` salen de la misma verificación roja y trabajaron en
paralelo.

## Tabla de `evaluate`

| Configuración | Calidad | Costo (USD) | Tokens de entrada |
| --- | --- | --- | --- |
| Línea base (sin palancas) | 100 % | 0.000918 | 1681 |
| Con palancas | 100 % | 0.000123 | 1111 |

La tabla no cambió respecto a la sesión 3: la sesión 4 agrega seguridad y despliegue, no toca las
palancas de costo. Se usa el modelo simulado, así que solo demuestra el ahorro de costo.

## Prueba de humo en producción

La persona la corrió en su propia terminal, para que la clave no pasara por el chat:

```
  [OK] GET /health -> 200 (esperado 200)
  [OK] POST /ask sin clave -> 401 (esperado 401)
  [OK] POST /ask con clave -> 200 (esperado 200)
[OK] production
```

Por eso esta prueba no aparece en `output/pipeline.md`, que solo registra lo que corre la fábrica.

## Bitácora

Los pasos 1 a 8 se corrieron el 2026-11-14 en otra conversación; se reconstruyen con
`output/activity.jsonl` y `output/pipeline.md`.

1. **Plan.** `architect` reescribió `output/plan.md` y agregó los ADR 0010, 0011 y 0012.
2. **Aprobación del plan.** La persona aprobó el plan.
3. **Pruebas primero.** `qa-unit` agregó las pruebas de seguridad y producción. `verification
   unit` falló: rojo, como se esperaba.
4. **Especialistas en paralelo.**
   - `security` agregó `auth.py`, `ratelimit.py`, `compliance.py` y `errors.py`, además del campo de
     clave en la página.
   - `deploy` agregó el `Dockerfile`, `.dockerignore`, `.gitignore`, `render.yaml`, el CI en
     `.github/workflows/` y `scripts/smoke.py`.
   - `qa-e2e` actualizó las pruebas de punta a punta para escribir la clave.
5. **Unión y compuertas.**
   - Primera corrida: unit OK y contract OK; qa falló.
   - Corrección 1, hecha por `qa-unit`.
   - Segunda corrida: unit, contract, qa, e2e y evaluate, las cinco OK.
6. **Evaluador-optimizador.** `qa-style` escribió `output/qa-review.md` con APROBADO.
7. **Aprobación para publicar.** La persona aprobó; está en `output/approved.txt` (2026-11-14).
8. **Publicar.** `scripts/publish.py hr-assistant` subió el producto a
   https://github.com/chavalalo/hr-assistant. La persona conectó el Blueprint en Render y puso
   los secretos en Render > Environment.
9. **Humo y triage.**
   - Primera prueba: `POST /ask` con clave dio 401.
   - Ciclo 1 de triage: el dueño fue `persona`. El código estaba bien; el servicio en vivo no tenía
     la clave nueva de `smoke` en `API_KEYS`. La persona redesplegó en Render.
   - Segunda prueba: dio 400. La causa fue que, al pegar con `read -s`, la terminal metió marcas
     invisibles de pegado (bracketed paste) en `SMOKE_API_KEY`: 55 caracteres en lugar de 43, 8 de
     ellos inválidos. La persona cargó la clave con `pbpaste`.
   - Tercera prueba: las tres comprobaciones OK.
10. **Pipeline y reporte.** `scripts/pipeline.py` generó `output/pipeline.md` con 18 pasos.

## Pendientes

- **AI Gateway con autenticación.** El gateway `default` de Cloudflare exige el encabezado
  `cf-aig-authorization`, que el producto todavía no manda. Con `MODEL_PROVIDER=gateway` responde
  401. Se resuelve con una adenda a la especificación (variable opcional `CF_AIG_TOKEN`) que pase
  por la fábrica.
- **Repositorio anidado.** `scripts/publish.py` creó un repositorio git dentro de `product/`, con
  remoto en `chavalalo/hr-assistant`. El repositorio externo sigue guardando los archivos de
  `product/` normalmente.
- **Para cargar claves en la terminal**, usa `export SMOKE_API_KEY="$(pbpaste | tr -d '[:space:]')"`
  en lugar de pegar dentro de `read -s`.
