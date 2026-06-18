import logging
import os

logger = logging.getLogger("contextlens")

# Module-level flag so the missing-key warning fires at most once per process,
# regardless of how many traces are attempted.
_warned_missing_key: bool = False


class SDKConfig:
    def __init__(self) -> None:
        self.api_key: str = os.environ.get("CONTEXTLENS_API_KEY", "")
        self.api_url: str = os.environ.get(
            "CONTEXTLENS_API_URL", "http://localhost:8000"
        ).rstrip("/")
        self.timeout: float = float(os.environ.get("CONTEXTLENS_TIMEOUT", "5"))

        enabled_raw = os.environ.get("CONTEXTLENS_ENABLED", "true").lower()
        self.enabled: bool = enabled_raw not in ("false", "0", "no")


def get_config() -> SDKConfig:
    """Read config fresh from env vars on every call.

    Reading fresh (not caching a singleton) means env var changes between
    calls are respected — important for the test scenarios in the validation
    script where CONTEXTLENS_API_URL and CONTEXTLENS_ENABLED change at runtime.
    Cost is negligible: three os.environ lookups per trace.
    """
    return SDKConfig()


def warn_missing_key_once() -> None:
    """Log a warning the first time tracing is skipped due to a missing API key."""
    global _warned_missing_key
    if not _warned_missing_key:
        logger.warning(
            "ContextLens: CONTEXTLENS_API_KEY is not set. "
            "Tracing is disabled. Set the environment variable to enable."
        )
        _warned_missing_key = True


def reset_for_testing() -> None:
    """Reset the warn-once flag. Called by the validation script between scenarios."""
    global _warned_missing_key
    _warned_missing_key = False
