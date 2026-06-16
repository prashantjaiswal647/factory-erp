from __future__ import annotations

import os
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]


def media_root() -> Path:
    return Path(os.getenv("MEDIA_ROOT", "volumes/media")).resolve()


def authorized_signature_root() -> Path:
    return Path(
        os.getenv("AUTHORIZED_SIGNATURE_ROOT", str(media_root() / "factory_signatures"))
    ).resolve()


def legacy_signature_root() -> Path:
    return Path(
        os.getenv("LEGACY_SIGNATURE_ROOT", str(media_root() / "signatures"))
    ).resolve()
