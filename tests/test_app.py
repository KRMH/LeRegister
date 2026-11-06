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
    monkeypatch.setattr(app_module, "build_application", lambda s, c, st, q: pytest.fail("must not connect"))
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

    monkeypatch.setattr(app_module, "build_application", lambda s, c, st, q: Boom())
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

    monkeypatch.setattr(app_module, "build_application", lambda s, c, st, q: Ok())
    app_module.main()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_unopenable_database_exits_2_with_message(monkeypatch, tmp_path, capsys):
    clear(monkeypatch, tmp_path)
    monkeypatch.setenv("LEREGISTER_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("LEREGISTER_OWNER_ID", "1")
    monkeypatch.setenv("LEREGISTER_DB_PATH", str(tmp_path))
    monkeypatch.setattr(app_module, "build_application", lambda s, c, st, q: pytest.fail("must not connect"))
    with pytest.raises(SystemExit) as e:
        app_module.main()
    assert e.value.code == 2
    assert "database" in capsys.readouterr().err
