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
        decoded = base64.b32decode(padded, casefold=True, map01="I")
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
