"""Pruebas de ``app.main``: rutas de salud y página web."""

import os


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
