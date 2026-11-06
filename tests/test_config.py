import pytest

from leregister.config import ConfigError, Settings

BASE = {"LEREGISTER_BOT_TOKEN": "tok", "LEREGISTER_OWNER_ID": "42"}


def load(env, tmp_path):
    return Settings.load({**env, "LEREGISTER_ENV_FILE": str(tmp_path / "none.env")})


def test_defaults(tmp_path):
    s = load(BASE, tmp_path)
    assert (s.bot_token, s.owner_id, s.chalet_count, s.max_stay) == ("tok", 42, 40, 60)


@pytest.mark.parametrize("missing", ["LEREGISTER_BOT_TOKEN", "LEREGISTER_OWNER_ID"])
def test_missing_required_names_setting(missing, tmp_path):
    env = {k: v for k, v in BASE.items() if k != missing}
    with pytest.raises(ConfigError, match=missing):
        load(env, tmp_path)


def test_non_numeric_owner_id(tmp_path):
    with pytest.raises(ConfigError, match="LEREGISTER_OWNER_ID"):
        load({**BASE, "LEREGISTER_OWNER_ID": "abc"}, tmp_path)


def test_env_file_fallback_and_env_wins(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# c\nLEREGISTER_BOT_TOKEN="filetok"\nLEREGISTER_OWNER_ID=7\nLEREGISTER_MAX_STAY=30\n')
    s = Settings.load({"LEREGISTER_ENV_FILE": str(f), "LEREGISTER_OWNER_ID": "9"})
    assert (s.bot_token, s.owner_id, s.max_stay) == ("filetok", 9, 30)


def test_changed_owner_id_changes_accepted_account(tmp_path):
    assert load(BASE, tmp_path).owner_id == 42
    assert load({**BASE, "LEREGISTER_OWNER_ID": "43"}, tmp_path).owner_id == 43


def test_empty_env_var_does_not_mask_file_value(tmp_path):
    f = tmp_path / ".env"
    f.write_text("LEREGISTER_BOT_TOKEN=filetok\nLEREGISTER_OWNER_ID=7\n")
    s = Settings.load({"LEREGISTER_ENV_FILE": str(f), "LEREGISTER_BOT_TOKEN": ""})
    assert s.bot_token == "filetok"


def test_env_file_export_prefix_and_bom(tmp_path):
    f = tmp_path / ".env"
    f.write_bytes(b"\xef\xbb\xbfexport LEREGISTER_BOT_TOKEN=t\nexport LEREGISTER_OWNER_ID=5\n")
    s = Settings.load({"LEREGISTER_ENV_FILE": str(f)})
    assert (s.bot_token, s.owner_id) == ("t", 5)


def test_unreadable_env_file_is_config_error(tmp_path):
    f = tmp_path / ".env"
    f.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(ConfigError, match="Cannot read"):
        Settings.load({"LEREGISTER_ENV_FILE": str(f)})


@pytest.mark.parametrize("key", ["LEREGISTER_CHALET_COUNT", "LEREGISTER_MAX_STAY"])
@pytest.mark.parametrize("bad", ["0", "-3", "x"])
def test_invalid_optional_numbers(key, bad, tmp_path):
    with pytest.raises(ConfigError, match=key):
        load({**BASE, key: bad}, tmp_path)


def test_optional_overrides(tmp_path):
    s = load({**BASE, "LEREGISTER_CHALET_COUNT": "12", "LEREGISTER_MAX_STAY": "10"}, tmp_path)
    assert (s.chalet_count, s.max_stay) == (12, 10)
