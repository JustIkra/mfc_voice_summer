import subprocess
from collections.abc import Callable, Sequence

KEYCHAIN_SERVICE = "codex.mcp.mfc_voice_summer.totp"
KEYCHAIN_ACCOUNT = "default"
KEYCHAIN_LABEL = "MFC Voice Summer Codex TOTP"
SECURITY = "/usr/bin/security"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class KeychainNotConfiguredError(RuntimeError):
    pass


class KeychainAccessError(RuntimeError):
    pass


def load_seed(runner: Runner = subprocess.run) -> str:
    result = runner(
        [
            SECURITY,
            "find-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 44:
        raise KeychainNotConfiguredError("TOTP seed is not configured.")
    if result.returncode != 0:
        raise KeychainAccessError("TOTP seed could not be read from macOS Keychain.")
    seed = result.stdout.strip()
    if not seed:
        raise KeychainAccessError("Stored TOTP seed is empty.")
    return seed


def store_seed_interactively(runner: Runner = subprocess.run) -> None:
    command: Sequence[str] = [
        SECURITY,
        "add-generic-password",
        "-U",
        "-a",
        KEYCHAIN_ACCOUNT,
        "-s",
        KEYCHAIN_SERVICE,
        "-l",
        KEYCHAIN_LABEL,
        "-w",
    ]
    result = runner(command, check=False)
    if result.returncode != 0:
        raise KeychainAccessError("TOTP seed was not stored in macOS Keychain.")
