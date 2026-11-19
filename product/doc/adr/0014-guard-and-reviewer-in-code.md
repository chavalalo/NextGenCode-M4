# 0014 Guardián de entrada y revisor de salida en código

Estado: propuesto (reto)

## Contexto

El asistente recibe texto libre del personal y responde con datos de RH. Hay que frenar el
prompt injection, evitar que datos personales (correo, teléfono, CURP, RFC, tarjeta, NSS)
lleguen al modelo, al log o a la traza, y no publicar respuestas que citen empleados que no
existen. Pedirle esto a otro modelo cuesta, es lento y no es determinista.

## Decisión

- `app/guard.py` corre antes que cualquier modelo: frases de injection normalizadas en la
  pregunta y en los mensajes `user` del historial -> `400 request blocked by input policy`.
  Después redacta la PII con `app/pii.py` (expresiones regulares y Luhn) y la petición sigue.
- `app/reviewer.py` corre al final: redacta PII, reemplaza la respuesta si menciona un
  `EMP-dddd` que no está en el directorio y la recorta a `MAX_ANSWER_CHARS`.
- Cada acción deja un `audit` con tipos y conteos, nunca valores; los contadores van a
  `/metrics` en `security`.

## Consecuencias

- Controles deterministas, sin costo de tokens y con pruebas unitarias por regla.
- Las listas de frases y patrones no cubren todo; se amplían con evidencia (`blocked_inputs`).
- Puede haber falsos positivos; el error es claro y se ve en la auditoría.
