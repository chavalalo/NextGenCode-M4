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


def test_default_observability_settings_are_safe():
    settings = Settings.from_env({})

    assert settings.service_name == "hr-assistant"
    assert settings.slo_p95_ms == 2000
    assert settings.hide_inputs is True
    assert settings.hide_outputs is True
    assert settings.tracing_enabled is False


def test_invalid_slo_or_hide_flag_prevents_startup():
    with pytest.raises(ConfigError, match="SLO_P95_MS"):
        Settings.from_env({"SLO_P95_MS": "0"})
    with pytest.raises(ConfigError, match="HIDE_INPUTS"):
        Settings.from_env({"HIDE_INPUTS": "quizas"})


def test_settings_never_keep_the_langsmith_key():
    secret = "lsv2-very-secret-key"
    settings = Settings.from_env(
        {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": secret}
    )

    assert settings.tracing_enabled is True
    assert secret not in repr(settings)
    assert secret not in [str(value) for value in vars(settings).values()]
