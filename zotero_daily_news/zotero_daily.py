#!/usr/bin/env python3
"""Unified packaged entry point."""

from __future__ import annotations

import sys


def main() -> None:
    if "--serve-only" in sys.argv[1:]:
        from .app import app
        from .launcher import PORT

        app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)
        return

    digest_flags = {
        "-h",
        "--help",
        "--dry-run",
        "--metadata-only",
        "--force",
        "--test-notify",
        "--verbose-notify",
        "--diagnose-notify",
        "--no-notify",
        "--refresh-queue",
        "--prepare-queue",
        "--push-queue",
        "--serve-only",
    }
    if any(arg in digest_flags for arg in sys.argv[1:]):
        from .digest import main as digest_main

        digest_main()
        return
    from .launcher import main as launcher_main

    launcher_main()


if __name__ == "__main__":
    main()
