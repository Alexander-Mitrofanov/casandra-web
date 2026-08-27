"""Retention cleanup entry point."""

from __future__ import annotations

from .config import Settings
from .db import Store
from .service import JobService


def main() -> None:
    settings = Settings.from_env()
    store = Store(settings)
    store.initialize()
    removed = JobService(settings, store).cleanup_expired()
    print(f"removed {removed} expired CasAndra web job(s)")


if __name__ == "__main__":
    main()
