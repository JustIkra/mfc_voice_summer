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
