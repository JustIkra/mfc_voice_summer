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
