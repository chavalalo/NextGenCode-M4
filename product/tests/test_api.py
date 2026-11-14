"""Pruebas de ``app.main``: rutas de salud, métricas y página web."""

import os
import uuid


def test_health_reports_ok_and_the_process_id(make_client):
    response = make_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "pid": os.getpid()}


def test_home_page_has_the_form_and_never_uses_inner_html(make_client):
    response = make_client().get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    for test_id in ("question", "send", "answer"):
        assert f'data-testid="{test_id}"' in response.text
    assert "innerHTML" not in response.text


def test_metrics_endpoint_has_exactly_the_specified_keys(make_observed_client):
    response = make_observed_client().get("/metrics")

    assert response.status_code == 200
    metrics = response.json()
    assert set(metrics) == {
        "pid", "requests", "error_rate", "latency_ms", "tokens", "slo"
    }
    assert metrics["pid"] == os.getpid()
    assert set(metrics["latency_ms"]) == {"p50", "p95"}
    assert set(metrics["tokens"]) == {"input", "output"}
    assert set(metrics["slo"]) == {"p95_ms_target", "met"}
    assert uuid.UUID(response.headers["X-Request-ID"])
