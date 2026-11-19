"""Prueba de carga local: muchas peticiones concurrentes contra el producto (reto).

Arranca el producto con el modelo simulado y manda ``REQUESTS`` peticiones a
``POST /ask`` con ``CONCURRENCY`` hilos. Pasa si todas responden ``200``.
Imprime p50, p95 y peticiones por segundo para la evidencia de concurrencia.
"""

import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from verification.server import running_product

PORT = 8777
REQUESTS = 60
CONCURRENCY = 10
QUESTIONS = (
    "¿Quién es EMP-0004?",
    "¿Cuántos días de vacaciones me tocan?",
    "¿Quiénes trabajan en el departamento de Finanzas?",
    "Compara a los empleados del departamento de Tecnología",
)


def main() -> int:
    """Corre la carga, imprime el resumen y decide."""
    with running_product(PORT) as client:

        def one(index):
            start = time.perf_counter()
            response = client.post(
                "/ask", json={"question": QUESTIONS[index % len(QUESTIONS)]}
            )
            return response.status_code, (time.perf_counter() - start) * 1000

        began = time.perf_counter()
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            results = list(pool.map(one, range(REQUESTS)))
        elapsed = time.perf_counter() - began
    codes = [code for code, _ in results]
    latencies = sorted(ms for _, ms in results)
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    print(
        f"requests={REQUESTS} concurrency={CONCURRENCY} "
        f"ok={codes.count(200)} p50_ms={statistics.median(latencies):.1f} "
        f"p95_ms={p95:.1f} rps={REQUESTS / elapsed:.1f}"
    )
    return 0 if codes == [200] * REQUESTS else 1


if __name__ == "__main__":
    sys.exit(main())
