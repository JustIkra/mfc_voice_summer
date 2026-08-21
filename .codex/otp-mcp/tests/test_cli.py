from project_otp_mcp import cli


def test_setup_invokes_interactive_keychain_store(monkeypatch, capsys) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(cli, "store_seed_interactively", lambda: calls.append(True))
    assert cli.main(["setup"]) == 0
    assert calls == [True]
    assert "stored in macOS Keychain" in capsys.readouterr().out


def test_setup_returns_failure_without_raw_exception(monkeypatch, capsys) -> None:
    def fail() -> None:
        raise cli.KeychainAccessError("private-marker")

    monkeypatch.setattr(cli, "store_seed_interactively", fail)
    assert cli.main(["setup"]) == 1
    captured = capsys.readouterr()
    assert "private-marker" not in captured.err
