from collections.abc import Sequence
from subprocess import CompletedProcess

import pytest

from project_otp_mcp.keychain import (
    KEYCHAIN_ACCOUNT,
    KEYCHAIN_SERVICE,
    KeychainAccessError,
    KeychainNotConfiguredError,
    load_seed,
    store_seed_interactively,
)


class FakeRunner:
    def __init__(self, result: CompletedProcess[str]) -> None:
        self.result = result
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, args: Sequence[str], **kwargs: object) -> CompletedProcess[str]:
        self.calls.append((list(args), kwargs))
        return self.result


def test_load_seed_returns_trimmed_stdout() -> None:
    runner = FakeRunner(CompletedProcess([], 0, stdout="ABC234\n", stderr=""))
    assert load_seed(runner=runner) == "ABC234"
    assert runner.calls[0][0] == [
        "/usr/bin/security",
        "find-generic-password",
        "-a",
        KEYCHAIN_ACCOUNT,
        "-s",
        KEYCHAIN_SERVICE,
        "-w",
    ]


def test_load_seed_maps_missing_item_without_exposing_stderr() -> None:
    marker = "private-marker"
    runner = FakeRunner(CompletedProcess([], 44, stdout="", stderr=marker))
    with pytest.raises(KeychainNotConfiguredError) as error:
        load_seed(runner=runner)
    assert marker not in str(error.value)


def test_load_seed_maps_other_failures_without_exposing_stderr() -> None:
    marker = "private-marker"
    runner = FakeRunner(CompletedProcess([], 1, stdout="", stderr=marker))
    with pytest.raises(KeychainAccessError) as error:
        load_seed(runner=runner)
    assert marker not in str(error.value)


def test_store_seed_uses_security_prompt_as_last_argument() -> None:
    runner = FakeRunner(CompletedProcess([], 0, stdout="", stderr=""))
    store_seed_interactively(runner=runner)
    args, kwargs = runner.calls[0]
    assert args[-1] == "-w"
    assert "secret" not in " ".join(args).lower()
    assert kwargs == {"check": False}
