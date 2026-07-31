# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compatibility entry point for older macOS packaging scripts.

AnySpark 3.2.1 uses the cross-platform desktop WebView shell.
"""

from desktop_launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
