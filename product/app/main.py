"""API web sin estado del HR Assistant.

``create_app`` recibe sus dependencias para que las pruebas inyecten las suyas;
``app`` es la instancia que arranca uvicorn con la configuración del entorno.
"""

import os
from pathlib import Path
from typing import List, Literal

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from app.agent import Agent
from app.config import Settings
from app.directory import EmployeeDirectory
from app.llm import build_model

INDEX_PATH = Path(__file__).resolve().parent / "static" / "index.html"


class HistoryMessage(BaseModel):
    """Mensaje previo de la conversación que guarda el navegador.

    :param role: ``user`` o ``assistant``
    :type role: str
    :param content: Texto del mensaje
    :type content: str
    """

    role: Literal["user", "assistant"]
    content: str


class AskResponse(BaseModel):
    """Respuesta de ``POST /ask``.

    :param answer: Respuesta en español
    :type answer: str
    :param steps: Vueltas que dio el agente
    :type steps: int
    :param tools_used: Herramientas usadas, en orden
    :type tools_used: list[str]
    :param input_tokens: Tokens de entrada
    :type input_tokens: int
    :param output_tokens: Tokens de salida
    :type output_tokens: int
    """

    answer: str
    steps: int
    tools_used: List[str]
    input_tokens: int
    output_tokens: int


def _build_ask_request(max_question_chars):
    """Crea el modelo de la petición con el largo máximo configurado.

    :param max_question_chars: Largo máximo de la pregunta
    :type max_question_chars: int
    :return: Clase Pydantic de la petición
    :rtype: type
    """

    class AskRequest(BaseModel):
        """Cuerpo de ``POST /ask``.

        :param question: Pregunta de la persona
        :type question: str
        :param history: Vueltas anteriores enviadas por el cliente
        :type history: list[HistoryMessage]
        """

        question: str = Field(max_length=max_question_chars)
        history: List[HistoryMessage] = Field(default_factory=list)

        @field_validator("question")
        @classmethod
        def question_not_blank(cls, value):
            """Rechaza preguntas vacías o solo con espacios.

            :param value: Pregunta recibida
            :type value: str
            :return: La pregunta sin cambios
            :rtype: str
            :raises ValueError: Si la pregunta está vacía
            """
            if not value.strip():
                raise ValueError("question must not be empty")
            return value

    return AskRequest


def create_app(settings=None, model=None, directory=None):
    """Arma la aplicación FastAPI con sus dependencias.

    :param settings: Configuración; si falta se lee del entorno
    :type settings: app.config.Settings or None
    :param model: Modelo de lenguaje; si falta se construye según la configuración
    :type model: app.llm.LanguageModel or None
    :param directory: Directorio de empleados; si falta se carga del archivo
    :type directory: app.directory.EmployeeDirectory or None
    :return: Aplicación lista para servir
    :rtype: fastapi.FastAPI
    :raises app.config.ConfigError: Si la configuración del entorno es inválida
    """
    settings = settings or Settings.from_env(os.environ)
    directory = directory or EmployeeDirectory(settings.employees_path)
    model = model or build_model(settings, directory.departments())
    agent = Agent(model=model, directory=directory, max_steps=settings.agent_max_steps)
    ask_request = _build_ask_request(settings.max_question_chars)
    index_html = INDEX_PATH.read_text(encoding="utf-8")

    application = FastAPI(title="HR Assistant")

    @application.get("/", response_class=HTMLResponse)
    def home():
        """Sirve la página web."""
        return HTMLResponse(index_html)

    @application.get("/health")
    def health():
        """Informa que el proceso está vivo y su id."""
        return {"status": "ok", "pid": os.getpid()}

    @application.post("/ask", response_model=AskResponse)
    def ask(request: ask_request):
        """Responde una pregunta; el historial lo manda el cliente."""
        messages = [message.model_dump() for message in request.history]
        messages.append({"role": "user", "content": request.question})
        result = agent.run(messages)
        return AskResponse(
            answer=result.answer,
            steps=result.steps,
            tools_used=list(result.tools_used),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    return application


app = create_app()
