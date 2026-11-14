"""Pruebas de punta a punta de la página del HR Assistant (spec/03-costs.md).

Se corren con el producto vivo y el modelo simulado; la URL base la pone la verificación.
"""

import re

from playwright.sync_api import Page, expect

FIRST_QUESTION = "¿Quién es EMP-0001?"
SECOND_QUESTION = "¿En qué departamento trabaja EMP-0002?"
REQUEST_ID_PATTERN = re.compile(r"\S{8,}")
EMPTY_QUESTION_MESSAGE = "Escribe una pregunta antes de enviar."


def _send(page: Page, question: str) -> None:
    """Escribe una pregunta en la página y la envía.

    :param page: Página de Playwright abierta en el producto
    :type page: Page
    :param question: Texto de la pregunta
    :type question: str
    """
    page.get_by_test_id("question").fill(question)
    page.get_by_test_id("send").click()


def test_asking_a_question_shows_the_answer_and_its_request_id(page: Page) -> None:
    """Una pregunta enviada muestra la respuesta y su ``request_id``."""
    page.goto("/")
    _send(page, FIRST_QUESTION)

    request_id = page.get_by_test_id("request-id")
    expect(request_id).to_have_count(1)
    expect(request_id).to_contain_text(REQUEST_ID_PATTERN)
    answer = page.get_by_test_id("answer")
    expect(answer).to_contain_text(FIRST_QUESTION)
    expect(answer).to_contain_text("EMP-0001")
    expect(answer).not_to_contain_text("No se pudo obtener una respuesta")


def test_sending_an_empty_question_shows_an_error_in_spanish(page: Page) -> None:
    """Una pregunta vacía muestra un mensaje de error en español y no llama a la API."""
    page.goto("/")
    page.get_by_test_id("question").fill("   ")
    page.get_by_test_id("send").click()

    expect(page.get_by_test_id("answer")).to_contain_text(EMPTY_QUESTION_MESSAGE)
    expect(page.get_by_test_id("request-id")).to_have_count(0)


def test_a_second_question_keeps_the_previous_conversation_on_screen(
    page: Page,
) -> None:
    """La segunda pregunta se agrega sin borrar la conversación anterior."""
    page.goto("/")
    _send(page, FIRST_QUESTION)
    expect(page.get_by_test_id("request-id")).to_have_count(1)
    _send(page, SECOND_QUESTION)

    expect(page.get_by_test_id("request-id")).to_have_count(2)
    answer = page.get_by_test_id("answer")
    expect(answer).to_contain_text(FIRST_QUESTION)
    expect(answer).to_contain_text(SECOND_QUESTION)
