"""HMAC-SHA256 signing for pickle artifacts.

Pickle deserialization executes arbitrary code. Our model load path (both
local disk and S3) is exposed to anything with write access to either — so
artifacts must be signed at save time and verified at load time.

Key source: env var MODEL_SIGNING_KEY (any bytestring, 32+ chars recommended).
If the key is not set, `verify()` returns False without raising — the caller
decides whether to fall back to unverified load (legacy compatibility) or
fail hard. Production deployments should set the key and refuse unverified
loads; set MODEL_REQUIRE_SIGNED=1 to enforce that globally.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_key() -> bytes | None:
    key = os.environ.get("MODEL_SIGNING_KEY")
    return key.encode("utf-8") if key else None


def require_signed() -> bool:
    return os.environ.get("MODEL_REQUIRE_SIGNED", "").strip() in ("1", "true", "TRUE", "yes")


def _sig_path(artifact_path: Path) -> Path:
    return artifact_path.with_suffix(artifact_path.suffix + ".sig")


def sign_artifact(artifact_path: Path) -> Path | None:
    """Compute HMAC-SHA256 over artifact bytes and write a sidecar .sig file.

    Returns the sig path, or None if no signing key is configured (unsigned
    artifact — a warning is logged).
    """
    key = _get_key()
    if key is None:
        logger.warning(
            "MODEL_SIGNING_KEY not set — writing %s without a signature. "
            "Downstream loads will fall back to unverified pickle unless "
            "MODEL_REQUIRE_SIGNED=1 is set on the server.",
            artifact_path,
        )
        return None

    mac = hmac.new(key, msg=artifact_path.read_bytes(), digestmod=hashlib.sha256)
    sig_path = _sig_path(artifact_path)
    sig_path.write_text(mac.hexdigest())
    logger.debug("Signed %s -> %s", artifact_path, sig_path)
    return sig_path


def verify_artifact(artifact_path: Path) -> bool:
    """Return True iff the artifact's sidecar .sig matches its HMAC.

    Returns False (without raising) when:
      - MODEL_SIGNING_KEY is not configured
      - the sig file is missing
      - the signature does not match
    """
    key = _get_key()
    if key is None:
        return False

    sig_path = _sig_path(artifact_path)
    if not sig_path.exists():
        return False

    expected = hmac.new(
        key, msg=artifact_path.read_bytes(), digestmod=hashlib.sha256
    ).hexdigest()
    try:
        actual = sig_path.read_text().strip()
    except OSError:
        return False
    return hmac.compare_digest(expected, actual)


def ensure_verified_or_fail(artifact_path: Path) -> None:
    """Raise if MODEL_REQUIRE_SIGNED is set and the artifact is unverified.

    Call this at the top of load() paths.
    """
    if not require_signed():
        return
    if not verify_artifact(artifact_path):
        raise RuntimeError(
            f"Refusing to unpickle unverified artifact {artifact_path} "
            "(MODEL_REQUIRE_SIGNED=1). Ensure the .sig sidecar is present "
            "and MODEL_SIGNING_KEY matches the signer."
        )
