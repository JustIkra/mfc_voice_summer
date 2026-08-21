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
