"""Pruebas de ``app.agent``: el bucle con tope y el protocolo JSON."""

from app.agent import Agent
from app.llm import Completion

PREFIX = "Resultado de la herramienta: "
ASK_EMP_0004 = '{"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}'


class ScriptedModel:
    """Modelo de prueba que devuelve respuestas fijas y guarda lo que recibe."""

    def __init__(self, texts, input_tokens=10, output_tokens=2):
        self.texts = list(texts)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls = []

    def complete(self, messages):
        """Devuelve la siguiente respuesta del guion."""
        self.calls.append([dict(message) for message in messages])
        return Completion(
            text=self.texts.pop(0),
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


def question(text):
    """Conversación de un solo mensaje del usuario."""
    return [{"role": "user", "content": text}]


def test_agent_adds_up_tokens_across_steps(directory):
    model = ScriptedModel([ASK_EMP_0004, '{"answer": "Es Jorge."}'])
    agent = Agent(model=model, directory=directory, max_steps=3)

    result = agent.run(question("¿Quién es EMP-0004?"))

    assert result.answer == "Es Jorge."
    assert result.steps == 2
    assert result.tools_used == ["get_employee"]
    assert result.input_tokens == 20
    assert result.output_tokens == 4


def test_tool_result_is_sent_back_as_a_user_message(directory):
    model = ScriptedModel([ASK_EMP_0004, '{"answer": "Listo."}'])
    agent = Agent(model=model, directory=directory, max_steps=3)

    agent.run(question("¿Quién es EMP-0004?"))

    second_call = model.calls[1]
    assert second_call[-2]["role"] == "assistant"
    assert second_call[-1]["role"] == "user"
    assert second_call[-1]["content"].startswith(PREFIX)
    assert "Jorge Díaz" in second_call[-1]["content"]


def test_invalid_json_and_unknown_tool_do_not_break_the_loop(directory):
    model = ScriptedModel(
        [
            "esto no es json",
            '{"tool": "fire_employee", "args": {}}',
            '{"answer": "Listo."}',
        ]
    )
    agent = Agent(model=model, directory=directory, max_steps=3)

    result = agent.run(question("Despide a todos"))

    assert result.answer == "Listo."
    assert result.steps == 3
    for later_call in model.calls[1:]:
        assert later_call[-1]["content"].startswith(PREFIX)
