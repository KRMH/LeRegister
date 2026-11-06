import logging

import pytest
from telegram.error import InvalidToken

import leregister.app as app_module


def clear(monkeypatch, tmp_path):
    for k in ("LEREGISTER_BOT_TOKEN", "LEREGISTER_OWNER_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LEREGISTER_ENV_FILE", str(tmp_path / "none.env"))
    monkeypatch.setenv("LEREGISTER_DB_PATH", str(tmp_path / "test.db"))


def test_missing_setting_exits_2_naming_it(monkeypatch, tmp_path, capsys):
    clear(monkeypatch, tmp_path)
    monkeypatch.setattr(app_module, "build_application", lambda s, c, st, q, i=None: pytest.fail("must not connect"))
    with pytest.raises(SystemExit) as e:
        app_module.main()
    assert e.value.code == 2
    assert "LEREGISTER_BOT_TOKEN" in capsys.readouterr().err


def test_rejected_token_exits_2_without_echoing_token(monkeypatch, tmp_path, capsys):
    clear(monkeypatch, tmp_path)
    monkeypatch.setenv("LEREGISTER_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("LEREGISTER_OWNER_ID", "1")

    class Boom:
        def run_polling(self):
            raise InvalidToken("123:secret")

    monkeypatch.setattr(app_module, "build_application", lambda s, c, st, q, i=None: Boom())
    with pytest.raises(SystemExit) as e:
        app_module.main()
    assert e.value.code == 2
    assert "secret" not in capsys.readouterr().err


def test_httpx_logs_silenced_at_startup(monkeypatch, tmp_path):
    clear(monkeypatch, tmp_path)
    monkeypatch.setenv("LEREGISTER_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("LEREGISTER_OWNER_ID", "1")

    class Ok:
        def run_polling(self):
            pass

    monkeypatch.setattr(app_module, "build_application", lambda s, c, st, q, i=None: Ok())
    app_module.main()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_unopenable_database_exits_2_with_message(monkeypatch, tmp_path, capsys):
    clear(monkeypatch, tmp_path)
    monkeypatch.setenv("LEREGISTER_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("LEREGISTER_OWNER_ID", "1")
    monkeypatch.setenv("LEREGISTER_DB_PATH", str(tmp_path))
    monkeypatch.setattr(app_module, "build_application", lambda s, c, st, q, i=None: pytest.fail("must not connect"))
    with pytest.raises(SystemExit) as e:
        app_module.main()
    assert e.value.code == 2
    assert "database" in capsys.readouterr().err


def _capture(monkeypatch):
    seen = {}

    class Ok:
        def run_polling(self):
            pass

    def fake(settings, clock, store, queue, interpreter=None):
        seen["interpreter"] = interpreter
        return Ok()

    monkeypatch.setattr(app_module, "build_application", fake)
    return seen


def test_a_key_turns_free_text_on_with_the_groq_adapter(monkeypatch, tmp_path):
    from leregister.adapters.llm import GroqInterpreter

    clear(monkeypatch, tmp_path)
    monkeypatch.setenv("LEREGISTER_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("LEREGISTER_OWNER_ID", "1")
    monkeypatch.setenv("LEREGISTER_LLM_API_KEY", "gsk_x")
    seen = _capture(monkeypatch)
    app_module.main()
    assert isinstance(seen["interpreter"], GroqInterpreter)


def test_no_key_means_no_interpreter(monkeypatch, tmp_path):
    clear(monkeypatch, tmp_path)
    monkeypatch.setenv("LEREGISTER_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("LEREGISTER_OWNER_ID", "1")
    monkeypatch.delenv("LEREGISTER_LLM_API_KEY", raising=False)
    seen = _capture(monkeypatch)
    app_module.main()
    assert seen["interpreter"] is None


def test_startup_says_whether_free_text_is_on_or_off(monkeypatch, tmp_path, caplog):
    import logging as _logging

    clear(monkeypatch, tmp_path)
    monkeypatch.setenv("LEREGISTER_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("LEREGISTER_OWNER_ID", "1")
    _capture(monkeypatch)
    monkeypatch.delenv("LEREGISTER_LLM_API_KEY", raising=False)
    with caplog.at_level(_logging.INFO):
        app_module.main()
    assert "free text is off" in caplog.text
    caplog.clear()
    monkeypatch.setenv("LEREGISTER_LLM_API_KEY", "gsk_x")
    with caplog.at_level(_logging.INFO):
        app_module.main()
    assert "free text is on" in caplog.text and "gsk_x" not in caplog.text
