"""Pruebas de ``app.config``: valores por omisión y validación."""

from pathlib import Path

import pytest

from app.config import ConfigError, Settings

PRODUCT = Path(__file__).resolve().parents[1]


def test_default_settings_match_the_specification():
    settings = Settings.from_env({})

    assert settings.model_provider == "fake"
    assert settings.agent_max_steps == 3
    assert settings.max_question_chars == 2000
    expected = (PRODUCT / "data" / "employees.json").resolve()
    assert Path(settings.employees_path).resolve() == expected


def test_zero_max_steps_prevents_startup():
    with pytest.raises(ConfigError, match="AGENT_MAX_STEPS"):
        Settings.from_env({"AGENT_MAX_STEPS": "0"})


def test_non_numeric_question_limit_prevents_startup():
    with pytest.raises(ConfigError, match="MAX_QUESTION_CHARS"):
        Settings.from_env({"MAX_QUESTION_CHARS": "mucho"})


def test_unknown_model_provider_prevents_startup():
    with pytest.raises(ConfigError, match="MODEL_PROVIDER"):
        Settings.from_env({"MODEL_PROVIDER": "openai"})
