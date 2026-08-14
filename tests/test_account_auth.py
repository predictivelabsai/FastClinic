"""Canonical account authentication and opt-in bootstrap coverage."""

from web.account_auth import AccountStore


def _configure_store(monkeypatch, path):
    monkeypatch.setenv("FASTCLINIC_OPS_BACKEND", "sqlite")
    monkeypatch.setenv("FASTSME_AUTH_DB", str(path))


def test_bootstrap_account_uses_the_normal_account_login(monkeypatch, tmp_path):
    path = tmp_path / "accounts.sqlite"
    _configure_store(monkeypatch, path)
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_AUTH_ENABLED", "true")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_EMAIL", "demo@example.test")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_PASSWORD", "a-secure-demo-password")

    store = AccountStore()

    account = store.login("demo@example.test", "a-secure-demo-password")
    assert account is not None
    assert account["is_verified"] == 1


def test_bootstrap_account_is_disabled_by_default(monkeypatch, tmp_path):
    path = tmp_path / "accounts.sqlite"
    _configure_store(monkeypatch, path)
    monkeypatch.delenv("FASTCLINIC_BOOTSTRAP_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_EMAIL", "demo@example.test")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_PASSWORD", "a-secure-demo-password")

    store = AccountStore()

    assert store.login("demo@example.test", "a-secure-demo-password") is None


def test_enabled_bootstrap_requires_explicit_valid_credentials(monkeypatch, tmp_path):
    path = tmp_path / "accounts.sqlite"
    _configure_store(monkeypatch, path)
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_AUTH_ENABLED", "true")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_EMAIL", "")
    monkeypatch.setenv("FASTCLINIC_BOOTSTRAP_PASSWORD", "short")

    try:
        AccountStore()
    except RuntimeError as exc:
        assert "Bootstrap auth requires" in str(exc)
    else:
        raise AssertionError("invalid bootstrap configuration should fail startup")
