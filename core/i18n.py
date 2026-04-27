"""
Internationalization (i18n) — multilingual support module.

Usage:
    from core.i18n import t
    print(t("search.no_results"))  # prints message in current locale

Locale configuration:
    config.json → "locale": "en" or "ko" (default: "en")
    env var: BIOAUTO_LOCALE=en
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Current locale (determined once at module level)
_current_locale: str = "en"

# Cached locale data from YAML files: {locale: {key: value}}
_locale_cache: dict[str, dict[str, str]] = {}

_LOCALES_DIR = Path(__file__).parent.parent / "locales"


def _load_locale_file(locale: str) -> dict[str, str]:
    """Load locales/{locale}.yaml. Returns empty dict if not found."""
    if locale in _locale_cache:
        return _locale_cache[locale]

    path = _LOCALES_DIR / f"{locale}.yaml"
    if not path.exists():
        _locale_cache[locale] = {}
        return {}

    try:
        import yaml  # type: ignore[import-untyped]
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        result = {k: str(v) for k, v in data.items() if v is not None}
        _locale_cache[locale] = result
        return result
    except Exception as exc:
        logger.warning("Failed to load locale file %s: %s", path, exc)
        _locale_cache[locale] = {}
        return {}


def _detect_locale() -> str:
    """Auto-detect locale. Priority: env var → config.json → default (en)."""
    # Environment variable
    env_locale = os.environ.get("BIOAUTO_LOCALE", "").strip().lower()
    if env_locale in ("en", "ko", "de", "ja"):
        return env_locale

    # config.json
    try:
        import json
        for p in [Path(__file__).parent.parent / "config.json", Path.cwd() / "config.json"]:
            if p.exists():
                with open(p) as f:
                    cfg = json.load(f)
                locale = cfg.get("locale", "").strip().lower()
                if locale in ("en", "ko", "de", "ja"):
                    return locale
                break
    except Exception:
        pass

    return "en"


def set_locale(locale: str) -> None:
    """Change locale at runtime."""
    global _current_locale
    if locale in ("en", "ko", "de", "ja"):
        _current_locale = locale
        logger.debug("Locale set to %s", locale)


def get_locale() -> str:
    """Return current locale."""
    return _current_locale


def t(key: str, **kwargs: Any) -> str:
    """Translate a message key to the current locale.

    Lookup order:
    1. locales/{locale}.yaml
    2. English fallback (locales/en.yaml)
    3. Key itself

    Args:
        key: Message key (e.g. "search.no_results")
        **kwargs: Format variables (e.g. count=5)

    Returns:
        Translated string. Returns the key itself if not found.
    """
    # 1. Current locale YAML
    locale_data = _load_locale_file(_current_locale)
    msg = locale_data.get(key)

    # 2. English fallback
    if msg is None and _current_locale != "en":
        en_data = _load_locale_file("en")
        msg = en_data.get(key)

    # 3. Key itself
    if msg is None:
        return key

    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except (KeyError, ValueError) as exc:
            logger.warning("Translation format error for key %s: %s", key, exc)

    return msg


# Auto-detect on module load
_current_locale = _detect_locale()
