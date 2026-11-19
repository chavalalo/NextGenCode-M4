persona

Qué falló: `POST /ask` con clave responde 401 en https://hr-assistant-1q29.onrender.com. `/health` da 200 y `/ask` sin clave da 401, así que el servicio está despierto, arrancó y la autenticación funciona.

Causa más probable: la clave de `SMOKE_API_KEY` no coincide exactamente con ninguna clave que el servicio en ejecución tiene cargada en `API_KEYS`. El código no tiene fallas. `app/auth.py` separa `cliente:clave` por comas, quita los espacios y compara el valor completo de `X-API-Key`. `verification/production.py` manda la clave en ese encabezado. El servicio arrancó con `ENVIRONMENT=production`, así que `API_KEYS` no está vacía y está bien formada en el deploy que corre ahora. La clave nueva simplemente no está en ese deploy.

Qué tiene que revisar la persona, sin compartir la clave con nadie:
1. En Render > hr-assistant > Environment, que `API_KEYS` incluya la entrada con prefijo de cliente, por ejemplo `smoke:<clave>`, separada por coma de las demás. Si se pegó la clave sola, sin `cliente:`, el valor queda mal formado.
2. Que el cambio se guardó con "Save, rebuild and deploy" (o "Save and deploy") y no con "Save only". Si se usó "Save only", lanza Manual Deploy > Deploy latest commit.
3. En Render > Events / Logs, que el último deploy terminó en "Live". Si falló al arrancar, por ejemplo con `API_KEYS entry N is malformed (length L)` o con un error de compliance (la clave necesita 16 caracteres o más), Render sigue sirviendo el deploy anterior, que no tiene la clave nueva. Corrige la entrada que indica el log y vuelve a desplegar.
4. En tu terminal, que `SMOKE_API_KEY` tenga exactamente la misma clave, sin el prefijo `cliente:`, sin comillas sobrantes ni saltos de línea, y que esté exportada en la misma sesión donde corres la prueba.
5. Vuelve a correr `uv run python -m verification production https://hr-assistant-1q29.onrender.com`.

Si después de esto el deploy está en "Live" con la clave correcta y todavía responde 401, vuelve a pasar el caso a triage con la línea `auth_rejected` del log de Render. Esa línea muestra el motivo y nunca la clave.
