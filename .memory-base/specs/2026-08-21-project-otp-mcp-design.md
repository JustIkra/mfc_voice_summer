# Project-scoped OTP MCP

## Purpose

Provide Codex with the current TOTP code for one account while keeping the TOTP seed out of the repository, Codex configuration, shell history, MCP arguments, and model context.

The integration applies only to the trusted `mfc_voice_summer` project. It does not read Apple Passwords and does not expose a network service.

## Architecture

The project contains a small Python package under `.codex/otp-mcp/`. It uses FastMCP over STDIO and is registered in the project-scoped `.codex/config.toml`.

The package has two entry points:

- `otp-mcp setup` launches `/usr/bin/security add-generic-password` with its interactive password prompt. The user enters the Base32 TOTP seed directly into the `security` process. The seed is never accepted as a command-line argument or by an MCP tool.
- `otp-mcp serve` starts the STDIO MCP server and exposes only `get_totp`.

The Keychain item uses service `codex.mcp.mfc_voice_summer.totp` and account `default`. The MCP process retrieves it with `/usr/bin/security find-generic-password`. The plaintext seed exists only transiently in process memory while calculating a code.

## MCP interface

`get_totp()` takes no arguments and returns structured data containing:

- `code`: the current six-digit TOTP code;
- `valid_for_seconds`: the number of whole seconds before the code changes.

The tool schema cannot accept or update a seed. The server exposes no resources, prompts, HTTP endpoints, token-management tools, or account enumeration.

Codex configuration restricts the server to `get_totp`, sets the default approval mode to `prompt`, and does not make successful MCP initialization mandatory for unrelated project work.

## TOTP behavior

The implementation uses Python standard-library primitives for RFC 6238:

- Base32 secret decoding;
- HMAC-SHA1;
- 30-second period;
- six decimal digits;
- dynamic truncation as defined by HOTP.

These parameters match the single account being configured. Supporting other algorithms, periods, digit lengths, HOTP counters, or multiple accounts is outside this version's scope.

The server uses the Mac system clock. Correct TOTP generation therefore depends on system time synchronization.

## Error handling

User-facing errors distinguish these cases without including secret material:

- Keychain item is missing;
- Keychain access is denied or cancelled;
- stored seed is empty or invalid Base32;
- the Keychain command fails unexpectedly.

The server never logs the seed, decoded seed bytes, complete Keychain output, environment variables, or generated `otpauth://` URIs. Error details returned over MCP are masked to the minimum needed for remediation.

## Security boundaries

- The seed is stored only in the user's macOS login Keychain.
- The generated OTP necessarily appears in the MCP result and Codex conversation context because the requested workflow requires Codex to use it.
- Tool invocation requires explicit Codex approval on every call.
- The server uses STDIO only and opens no listening port.
- `.codex/config.toml`, source code, tests, and lockfiles contain no real seed or generated production OTP.
- Package versions are locked with `uv.lock`; Codex does not execute an unpinned `npx -y` package on each launch.

This design protects the long-lived seed from normal project and MCP data flows. It does not protect against malware or another process already able to act as the logged-in macOS user and access that user's unlocked Keychain.

## Files

- `.codex/config.toml`: project-scoped MCP registration and tool approval policy.
- `.codex/otp-mcp/pyproject.toml`: isolated Python package metadata and dependencies.
- `.codex/otp-mcp/uv.lock`: resolved dependency lock.
- `.codex/otp-mcp/src/otp_mcp/`: Keychain adapter, TOTP calculation, CLI, and MCP server.
- `.codex/otp-mcp/tests/`: unit and CLI-level tests using fake secrets and Keychain responses.
- `.memory-base/plans/2026-08-21-project-otp-mcp.md`: implementation plan created after this specification is approved.

## Verification

Automated tests cover:

- RFC 6238 SHA-1 reference vectors;
- six-digit formatting and remaining-validity calculation;
- missing, denied, empty, and malformed Keychain values;
- the `get_totp` tool's no-argument schema and structured result;
- protection against emitting the seed in error messages.

Manual verification covers:

1. Running `otp-mcp setup` and confirming that input is not echoed.
2. Confirming no seed appears in process arguments, project files, or Codex configuration.
3. Restarting Codex in this repository and checking that the project MCP is available.
4. Approving one `get_totp` call and comparing its code with the same account's existing authenticator during the same 30-second window.
5. Opening Codex outside this repository and confirming the project-scoped server is not configured there.

## Success criteria

- Codex can request the current OTP for the configured account from this project.
- The real seed is entered only through a local hidden prompt and remains absent from repository files and model-visible tool calls.
- Every OTP retrieval requires user approval.
- The MCP server is unavailable outside this project.
- Automated and manual verification complete without exposing the real seed.
