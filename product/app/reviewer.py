"""Revisor de salida: PII, respuesta anclada al directorio y recorte.

En este orden: oculta la PII de la respuesta; si menciona un id ``EMP-dddd``
que no existe en el directorio, la reemplaza por un mensaje fijo; al final la
recorta a ``MAX_ANSWER_CHARS``. Nunca escribe el texto que revisa.
"""

import re
from dataclasses import dataclass

from app.pii import redact

EMPLOYEE_ID_PATTERN = re.compile(r"\bEMP-\d{4}\b", re.IGNORECASE)
UNVERIFIED_ANSWER = (
    "No pude verificar la respuesta con el directorio. Intenta de nuevo."
)
BLOCK_REASON = "unknown_employee_id"


@dataclass(frozen=True)
class Review:
    """Respuesta revisada y lo que hizo el revisor.

    :param answer: Respuesta final
    :type answer: str
    :param types: Tipos de PII ocultados, sin repetir y ordenados
    :type types: tuple[str, ...]
    :param count: Cuántos valores de PII se ocultaron
    :type count: int
    :param blocked: ``True`` si se reemplazó por el mensaje de verificación
    :type blocked: bool
    """

    answer: str
    types: tuple = ()
    count: int = 0
    blocked: bool = False


def mentions_unknown_employee(text, directory):
    """Indica si el texto cita un id de empleado que no existe.

    :param text: Respuesta del especialista
    :type text: str
    :param directory: Directorio de empleados
    :type directory: app.directory.EmployeeDirectory
    :return: ``True`` si algún id no está en el directorio
    :rtype: bool
    """
    return any(
        not directory.has_employee(match.group(0))
        for match in EMPLOYEE_ID_PATTERN.finditer(text)
    )


def review(answer, directory, max_chars):
    """Revisa la respuesta del especialista antes de mandarla.

    :param answer: Respuesta del especialista
    :type answer: str
    :param directory: Directorio de empleados
    :type directory: app.directory.EmployeeDirectory
    :param max_chars: Largo máximo de la respuesta
    :type max_chars: int
    :return: Respuesta revisada
    :rtype: Review
    """
    cleaned = redact(answer)
    blocked = mentions_unknown_employee(cleaned.text, directory)
    text = UNVERIFIED_ANSWER if blocked else cleaned.text
    return Review(
        answer=text[:max_chars],
        types=cleaned.types,
        count=cleaned.count,
        blocked=blocked,
    )
