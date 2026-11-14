"""Pruebas de ``app.llm``: reglas y tokens del modelo simulado."""

import json

PREFIX = "Resultado de la herramienta: "


def user(content):
    """Mensaje del rol ``user``."""
    return {"role": "user", "content": content}


def test_fake_model_asks_for_get_employee_when_it_sees_an_id(fake_model):
    completion = fake_model.complete([user("¿Quién es EMP-0004?")])

    assert json.loads(completion.text) == {
        "tool": "get_employee",
        "args": {"employee_id": "EMP-0004"},
    }


def test_fake_model_asks_for_a_department_search(fake_model):
    completion = fake_model.complete([user("¿Quiénes trabajan en Finanzas?")])

    request = json.loads(completion.text)
    assert request["tool"] == "search_by_department"
    assert request["args"] == {"department": "Finanzas"}


def test_fake_model_answers_with_the_tool_result(fake_model):
    tool_result = '{"id": "EMP-0005", "name": "Sofía Gómez"}'
    messages = [
        user("¿Quién es EMP-0005?"),
        {"role": "assistant", "content": '{"tool": "get_employee"}'},
        user(PREFIX + tool_result),
    ]

    completion = fake_model.complete(messages)

    assert json.loads(completion.text) == {
        "answer": "Según el directorio: " + tool_result
    }


def test_fake_model_counts_words_as_tokens(fake_model):
    messages = [
        user("hola a todos"),
        {"role": "assistant", "content": "buenas"},
        user("qué tal"),
    ]

    completion = fake_model.complete(messages)

    assert completion.input_tokens == 6
    assert completion.output_tokens == len(completion.text.split())
