# Project-scoped OTP MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project-scoped STDIO MCP server that retrieves one TOTP seed from macOS Keychain and returns the current six-digit code only after Codex approval.

**Architecture:** An isolated Python 3.12 package under `.codex/otp-mcp/` separates RFC 6238 calculation, macOS Keychain access, CLI setup, and FastMCP transport. The project `.codex/config.toml` starts the locked package over STDIO and allow-lists only `get_totp`; the real seed is provisioned interactively after the code is installed.

**Tech Stack:** Python 3.12, FastMCP 3.2.4, Python standard-library `base64`/`hashlib`/`hmac`/`subprocess`, macOS `/usr/bin/security`, uv, pytest, Ruff, TOML.

**Spec:** `.memory-base/specs/2026-08-21-project-otp-mcp-design.md`

## Global Constraints

- Scope the MCP registration to the trusted `mfc_voice_summer` project through `.codex/config.toml`.
- Store the seed only in the user's macOS login Keychain under service `codex.mcp.mfc_voice_summer.totp` and account `default`.
- Never accept the seed in an MCP argument, command-line argument, environment variable, config file, source file, test fixture, or log.
- Expose only a no-argument `get_totp` tool over STDIO; do not start HTTP, SSE, or another listener.
- Generate six digits with HMAC-SHA1 and a 30-second period.
- Require Codex approval for every tool call with `default_tools_approval_mode = "prompt"`.
- Lock Python dependencies in `.codex/otp-mcp/uv.lock` and launch with `uv run --locked`.
- Preserve unrelated working-tree changes, including `.memory-base/index.md`.

## File Structure

- `.codex/otp-mcp/pyproject.toml`: isolated package metadata, exact FastMCP dependency, development tools, and console entry point.
- `.codex/otp-mcp/uv.lock`: reproducible dependency resolution.
- `.codex/otp-mcp/src/project_otp_mcp/__init__.py`: package marker and public version.
- `.codex/otp-mcp/src/project_otp_mcp/totp.py`: pure RFC 6238 calculation and validation.
- `.codex/otp-mcp/src/project_otp_mcp/keychain.py`: the only module allowed to invoke `/usr/bin/security`.
- `.codex/otp-mcp/src/project_otp_mcp/server.py`: application service, error redaction, and FastMCP tool registration.
- `.codex/otp-mcp/src/project_otp_mcp/cli.py`: `setup` and `serve` commands.
- `.codex/otp-mcp/src/project_otp_mcp/__main__.py`: `python -m project_otp_mcp` entry point.
- `.codex/otp-mcp/tests/test_totp.py`: RFC vectors, formatting, validity, and invalid-seed tests.
- `.codex/otp-mcp/tests/test_keychain.py`: command construction and redacted Keychain failure tests.
- `.codex/otp-mcp/tests/test_server.py`: tool schema, structured output, and MCP error tests.
- `.codex/otp-mcp/tests/test_cli.py`: setup command behavior without real Keychain mutation.
- `.codex/otp-mcp/tests/test_project_config.py`: project MCP allow-list and approval-policy assertions.
- `.codex/config.toml`: project-scoped Codex MCP registration.

---

### Task 1: Isolated package and RFC 6238 core

**Files:**
- Create: `.codex/otp-mcp/pyproject.toml`
- Create: `.codex/otp-mcp/src/project_otp_mcp/__init__.py`
- Create: `.codex/otp-mcp/src/project_otp_mcp/totp.py`
- Create: `.codex/otp-mcp/tests/test_totp.py`

**Interfaces:**
- Consumes: a Base32 `str` seed and an optional Unix timestamp supplied by callers.
- Produces: `TotpResult(code: str, valid_for_seconds: int)`, `InvalidTotpSeedError`, and `generate_totp(secret: str, timestamp: float | None = None) -> TotpResult`.

- [ ] **Step 1: Create the isolated package metadata**

Create `.codex/otp-mcp/pyproject.toml`:

```toml
[project]
name = "mfc-project-otp-mcp"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["fastmcp==3.2.4"]

[project.scripts]
otp-mcp = "project_otp_mcp.cli:main"

[dependency-groups]
dev = ["pytest>=8.4,<9", "pytest-asyncio>=1,<2", "ruff>=0.12,<0.13"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/project_otp_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]
ignore = ["RUF001", "RUF002", "RUF003", "N818"]
```

Create `src/project_otp_mcp/__init__.py` with `__version__ = "0.1.0"`.

- [ ] **Step 2: Write failing RFC 6238 tests**

Create `.codex/otp-mcp/tests/test_totp.py`:

```python
import pytest

from project_otp_mcp.totp import InvalidTotpSeedError, generate_totp

RFC_SHA1_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [(59, "287082"), (1_111_111_109, "081804")],
)
def test_generate_totp_matches_rfc_6238_sha1_vectors(timestamp: int, expected: str) -> None:
    assert generate_totp(RFC_SHA1_SECRET, timestamp).code == expected


def test_generate_totp_reports_remaining_whole_seconds() -> None:
    assert generate_totp(RFC_SHA1_SECRET, 60).valid_for_seconds == 30
    assert generate_totp(RFC_SHA1_SECRET, 89.2).valid_for_seconds == 1


@pytest.mark.parametrize("secret", ["", "   ", "not*base32"])
def test_generate_totp_rejects_invalid_seed_without_echoing_it(secret: str) -> None:
    with pytest.raises(InvalidTotpSeedError) as error:
        generate_totp(secret, 59)
    assert str(error.value) in {
        "Stored TOTP seed is empty.",
        "Stored TOTP seed is invalid Base32.",
    }
```

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```bash
uv run --project .codex/otp-mcp pytest .codex/otp-mcp/tests/test_totp.py -q
```

Expected: collection fails because `project_otp_mcp.totp` does not exist.

- [ ] **Step 4: Implement the minimal TOTP core**

Create `.codex/otp-mcp/src/project_otp_mcp/totp.py`:

```python
import base64
import binascii
import hashlib
import hmac
import time
from dataclasses import dataclass

PERIOD_SECONDS = 30
CODE_MODULUS = 1_000_000


class InvalidTotpSeedError(ValueError):
    pass


@dataclass(frozen=True)
class TotpResult:
    code: str
    valid_for_seconds: int


def _decode_seed(secret: str) -> bytes:
    normalized = "".join(secret.split()).upper()
    if not normalized:
        raise InvalidTotpSeedError("Stored TOTP seed is empty.")
    padded = normalized + "=" * (-len(normalized) % 8)
    try:
        decoded = base64.b32decode(padded, casefold=True)
    except (binascii.Error, ValueError) as error:
        raise InvalidTotpSeedError("Stored TOTP seed is invalid Base32.") from error
    if not decoded:
        raise InvalidTotpSeedError("Stored TOTP seed is empty.")
    return decoded


def generate_totp(secret: str, timestamp: float | None = None) -> TotpResult:
    current_time = time.time() if timestamp is None else timestamp
    counter = int(current_time // PERIOD_SECONDS)
    digest = hmac.new(
        _decode_seed(secret),
        counter.to_bytes(8, byteorder="big"),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset : offset + 4], byteorder="big") & 0x7FFFFFFF
    code = f"{binary % CODE_MODULUS:06d}"
    valid_for_seconds = PERIOD_SECONDS - (int(current_time) % PERIOD_SECONDS)
    return TotpResult(code=code, valid_for_seconds=valid_for_seconds)
```

- [ ] **Step 5: Run core tests and quality checks**

Run:

```bash
uv run --project .codex/otp-mcp pytest .codex/otp-mcp/tests/test_totp.py -q
uv run --project .codex/otp-mcp ruff check .codex/otp-mcp
uv run --project .codex/otp-mcp ruff format --check .codex/otp-mcp
```

Expected: all tests pass and Ruff reports no issues.

- [ ] **Step 6: Commit the TOTP core**

```bash
git add .codex/otp-mcp/pyproject.toml .codex/otp-mcp/src/project_otp_mcp/__init__.py .codex/otp-mcp/src/project_otp_mcp/totp.py .codex/otp-mcp/tests/test_totp.py
git commit -m "feat: add project TOTP core"
```

---

### Task 2: macOS Keychain adapter and interactive setup

**Files:**
- Create: `.codex/otp-mcp/src/project_otp_mcp/keychain.py`
- Create: `.codex/otp-mcp/tests/test_keychain.py`

**Interfaces:**
- Consumes: `/usr/bin/security` through an injectable `Runner` callable compatible with `subprocess.run`.
- Produces: `load_seed() -> str`, `store_seed_interactively() -> None`, `KeychainNotConfiguredError`, and `KeychainAccessError`.

- [ ] **Step 1: Write failing Keychain tests**

Create `.codex/otp-mcp/tests/test_keychain.py` with a fake runner that records calls:

```python
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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
uv run --project .codex/otp-mcp pytest .codex/otp-mcp/tests/test_keychain.py -q
```

Expected: collection fails because `project_otp_mcp.keychain` does not exist.

- [ ] **Step 3: Implement the Keychain adapter**

Create `.codex/otp-mcp/src/project_otp_mcp/keychain.py`:

```python
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
```

- [ ] **Step 4: Run Keychain tests and inspect argument safety**

Run:

```bash
uv run --project .codex/otp-mcp pytest .codex/otp-mcp/tests/test_keychain.py -q
uv run --project .codex/otp-mcp ruff check .codex/otp-mcp
```

Expected: tests pass; the setup command's final argument is bare `-w`, which makes `/usr/bin/security` prompt instead of receiving a secret in argv.

- [ ] **Step 5: Commit the Keychain adapter**

```bash
git add .codex/otp-mcp/src/project_otp_mcp/keychain.py .codex/otp-mcp/tests/test_keychain.py
git commit -m "feat: store project TOTP seed in Keychain"
```

---

### Task 3: FastMCP tool and command-line entry point

**Files:**
- Create: `.codex/otp-mcp/src/project_otp_mcp/server.py`
- Create: `.codex/otp-mcp/src/project_otp_mcp/cli.py`
- Create: `.codex/otp-mcp/src/project_otp_mcp/__main__.py`
- Create: `.codex/otp-mcp/tests/test_server.py`
- Create: `.codex/otp-mcp/tests/test_cli.py`

**Interfaces:**
- Consumes: `load_seed() -> str`, `store_seed_interactively() -> None`, and `generate_totp(secret, timestamp) -> TotpResult`.
- Produces: `build_server(seed_loader, clock) -> FastMCP`, module-level `mcp`, and CLI commands `otp-mcp setup` and `otp-mcp serve`.

- [ ] **Step 1: Write failing in-process MCP tests**

Create `.codex/otp-mcp/tests/test_server.py`:

```python
from fastmcp import Client

from project_otp_mcp.keychain import KeychainAccessError, KeychainNotConfiguredError
from project_otp_mcp.server import build_server

RFC_SHA1_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


async def test_server_exposes_only_no_argument_get_totp() -> None:
    server = build_server(seed_loader=lambda: RFC_SHA1_SECRET, clock=lambda: 59)
    async with Client(server) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools] == ["get_totp"]
        assert tools[0].inputSchema["properties"] == {}
        result = await client.call_tool("get_totp", {})
    assert result.structured_content == {"code": "287082", "valid_for_seconds": 1}


async def test_server_redacts_keychain_failures() -> None:
    marker = "private-marker"

    def fail() -> str:
        raise KeychainAccessError(marker)

    server = build_server(seed_loader=fail, clock=lambda: 59)
    async with Client(server) as client:
        result = await client.call_tool("get_totp", {})
    assert result.is_error is True
    assert marker not in str(result.content)


async def test_server_explains_missing_configuration() -> None:
    def fail() -> str:
        raise KeychainNotConfiguredError("hidden")

    server = build_server(seed_loader=fail, clock=lambda: 59)
    async with Client(server) as client:
        result = await client.call_tool("get_totp", {})
    assert result.is_error is True
    assert "otp-mcp setup" in str(result.content)
```

- [ ] **Step 2: Write failing CLI tests**

Create `.codex/otp-mcp/tests/test_cli.py`:

```python
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
```

- [ ] **Step 3: Run MCP and CLI tests and verify RED**

Run:

```bash
uv run --project .codex/otp-mcp pytest .codex/otp-mcp/tests/test_server.py .codex/otp-mcp/tests/test_cli.py -q
```

Expected: collection fails because `server.py` and `cli.py` do not exist.

- [ ] **Step 4: Implement the FastMCP server with redacted errors**

Create `.codex/otp-mcp/src/project_otp_mcp/server.py`:

```python
import time
from collections.abc import Callable

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .keychain import KeychainAccessError, KeychainNotConfiguredError, load_seed
from .totp import InvalidTotpSeedError, TotpResult, generate_totp

SeedLoader = Callable[[], str]
Clock = Callable[[], float]


def build_server(
    seed_loader: SeedLoader = load_seed,
    clock: Clock = time.time,
) -> FastMCP:
    server = FastMCP(
        "mfc-project-otp",
        instructions="Generate the configured project's TOTP only after user approval.",
    )

    @server.tool(
        name="get_totp",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def get_totp() -> TotpResult:
        """Return the current TOTP code and its remaining lifetime."""
        try:
            return generate_totp(seed_loader(), clock())
        except KeychainNotConfiguredError:
            raise ToolError("TOTP seed is not configured. Run: otp-mcp setup") from None
        except KeychainAccessError:
            raise ToolError("TOTP seed could not be read from macOS Keychain.") from None
        except InvalidTotpSeedError:
            raise ToolError("Stored TOTP seed is invalid.") from None
        except Exception:
            raise ToolError("OTP generation failed.") from None

    return server


mcp = build_server()
```

- [ ] **Step 5: Implement the CLI and module entry point**

Create `.codex/otp-mcp/src/project_otp_mcp/cli.py`:

```python
import argparse
import sys
from collections.abc import Sequence

from .keychain import KeychainAccessError, store_seed_interactively
from .server import mcp


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="otp-mcp")
    parser.add_argument("command", choices=("setup", "serve"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "setup":
        try:
            store_seed_interactively()
        except KeychainAccessError:
            print("Unable to store TOTP seed in macOS Keychain.", file=sys.stderr)
            return 1
        print("TOTP seed stored in macOS Keychain.")
        return 0
    mcp.run(transport="stdio", show_banner=False)
    return 0
```

Create `.codex/otp-mcp/src/project_otp_mcp/__main__.py`:

```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 6: Run MCP and CLI tests**

Run:

```bash
uv run --project .codex/otp-mcp pytest .codex/otp-mcp/tests/test_server.py .codex/otp-mcp/tests/test_cli.py -q
```

Expected: five tests pass, including the exact tool-name, empty-input-schema, structured-content, and redaction assertions.

- [ ] **Step 7: Run the whole package suite and quality checks**

Run:

```bash
uv run --project .codex/otp-mcp pytest .codex/otp-mcp/tests -q
uv run --project .codex/otp-mcp ruff check .codex/otp-mcp
uv run --project .codex/otp-mcp ruff format --check .codex/otp-mcp
```

Expected: all tests pass and Ruff reports no issues.

- [ ] **Step 8: Commit the FastMCP surface**

```bash
git add .codex/otp-mcp/src/project_otp_mcp/server.py .codex/otp-mcp/src/project_otp_mcp/cli.py .codex/otp-mcp/src/project_otp_mcp/__main__.py .codex/otp-mcp/tests/test_server.py .codex/otp-mcp/tests/test_cli.py
git commit -m "feat: expose project TOTP over MCP"
```

---

### Task 4: Locked project registration and automated configuration checks

**Files:**
- Create: `.codex/config.toml`
- Create: `.codex/otp-mcp/uv.lock`
- Create: `.codex/otp-mcp/tests/test_project_config.py`

**Interfaces:**
- Consumes: the `otp-mcp serve` console entry point from Task 3.
- Produces: a project-only Codex MCP named `project_otp`, restricted to `get_totp` with per-call approval.

- [ ] **Step 1: Write a failing project-config test**

Create `.codex/otp-mcp/tests/test_project_config.py`:

```python
import tomllib
from pathlib import Path


def test_project_config_registers_only_approved_otp_tool() -> None:
    repository = Path(__file__).resolve().parents[3]
    config = tomllib.loads((repository / ".codex" / "config.toml").read_text())
    server = config["mcp_servers"]["project_otp"]
    assert server["command"] == "uv"
    assert server["args"] == [
        "run",
        "--locked",
        "--project",
        str(repository / ".codex" / "otp-mcp"),
        "otp-mcp",
        "serve",
    ]
    assert server["cwd"] == str(repository)
    assert server["enabled_tools"] == ["get_totp"]
    assert server["default_tools_approval_mode"] == "prompt"
    assert server["required"] is False
```

- [ ] **Step 2: Run the config test and verify RED**

Run:

```bash
uv run --project .codex/otp-mcp pytest .codex/otp-mcp/tests/test_project_config.py -q
```

Expected: failure because `.codex/config.toml` does not exist.

- [ ] **Step 3: Resolve and lock dependencies**

Run:

```bash
uv lock --project .codex/otp-mcp
uv sync --project .codex/otp-mcp --locked
```

Expected: `.codex/otp-mcp/uv.lock` is created and the environment syncs without changing it.

- [ ] **Step 4: Create the project-scoped Codex configuration**

Create `.codex/config.toml` with the resolved repository path `/Users/maksim/git_projects/mfc_voice_summer`:

```toml
[mcp_servers.project_otp]
command = "uv"
args = [
  "run",
  "--locked",
  "--project",
  "/Users/maksim/git_projects/mfc_voice_summer/.codex/otp-mcp",
  "otp-mcp",
  "serve",
]
cwd = "/Users/maksim/git_projects/mfc_voice_summer"
enabled_tools = ["get_totp"]
default_tools_approval_mode = "prompt"
required = false
```

- [ ] **Step 5: Run config and full package verification**

Run:

```bash
uv run --locked --project .codex/otp-mcp pytest .codex/otp-mcp/tests -q
uv run --locked --project .codex/otp-mcp ruff check .codex/otp-mcp
uv run --locked --project .codex/otp-mcp ruff format --check .codex/otp-mcp
git diff --check
```

Expected: all tests pass, Ruff reports no issues, and `git diff --check` is silent.

- [ ] **Step 6: Verify no secret-bearing configuration surface exists**

Run:

```bash
rg -n "secret|seed|otpauth|AUTHN8_API_KEY" .codex/config.toml .codex/otp-mcp/pyproject.toml
```

Expected: no matches. Source-code references to the generic terms `secret` and `seed` are expected only when separately reviewing implementation code; no real seed value may appear anywhere in the repository.

- [ ] **Step 7: Confirm Codex parses the project MCP configuration**

Run from `/Users/maksim/git_projects/mfc_voice_summer`:

```bash
codex mcp get project_otp
```

Expected: Codex reports an enabled STDIO server whose command is `uv`, whose tool allow-list contains only `get_totp`, and whose approval mode is `prompt`.

- [ ] **Step 8: Commit the locked project integration**

```bash
git add .codex/config.toml .codex/otp-mcp/uv.lock .codex/otp-mcp/tests/test_project_config.py
git commit -m "chore: connect project OTP MCP"
```

---

### Task 5: Provision the real seed and perform end-to-end validation

**Files:**
- Modify: macOS login Keychain item `codex.mcp.mfc_voice_summer.totp/default` outside the repository.
- Verify: `.codex/config.toml` and `.codex/otp-mcp/` without writing the seed to disk.

**Interfaces:**
- Consumes: the user's Base32 TOTP seed through `/usr/bin/security`'s hidden interactive prompt.
- Produces: a Keychain-backed `get_totp()` result available only to this project's Codex MCP.

- [ ] **Step 1: Provision the seed through the hidden Keychain prompt**

Run interactively from the repository root:

```bash
uv run --locked --project .codex/otp-mcp otp-mcp setup
```

Expected: `/usr/bin/security` prompts for the seed without echoing it and then prints only `TOTP seed stored in macOS Keychain.` Never paste the seed into chat.

- [ ] **Step 2: Confirm the Keychain item exists without printing its value**

Run:

```bash
/usr/bin/security find-generic-password -a default -s codex.mcp.mfc_voice_summer.totp
```

Expected: metadata for one matching generic-password item; do not add `-w` during this check.

- [ ] **Step 3: Restart the Codex client and validate project scope**

Restart the ChatGPT desktop app, Codex CLI session, or IDE extension while its working directory is `/Users/maksim/git_projects/mfc_voice_summer`, then open `/mcp` or run `codex mcp get project_otp`.

Expected: `project_otp` is enabled in this project. From an unrelated trusted project, `project_otp` is absent because no global `~/.codex/config.toml` entry was created.

- [ ] **Step 4: Perform the user-approved real-code comparison**

Ask Codex to call `get_totp`, approve that one call, and compare the returned six-digit code with the existing authenticator during the same 30-second window.

Expected: codes match. Do not record the code in a source file, test fixture, issue, or commit.

- [ ] **Step 5: Final repository and history audit**

Run:

```bash
git status --short
git log -5 --oneline
git diff --check
```

Expected: only pre-existing unrelated changes remain unstaged, the implementation commits are present, and no whitespace errors are reported. No commit is created for Keychain provisioning because it changes no repository file.
