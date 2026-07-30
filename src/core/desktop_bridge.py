# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small in-process bridge between the HTTP server and desktop window.

The API deliberately exposes only an activation signal. It contains no window
objects, so importing the FastAPI application never imports a GUI framework.
"""

from __future__ import annotations

import threading

_activation_requested = threading.Event()


def request_activation() -> None:
    """Ask the owning desktop shell to restore and focus its window."""
    _activation_requested.set()


def wait_for_activation(timeout: float = 0.5) -> bool:
    """Wait for one activation request and consume it."""
    if not _activation_requested.wait(timeout):
        return False
    _activation_requested.clear()
    return True


def clear_activation() -> None:
    """Clear a stale signal before a newly created window starts listening."""
    _activation_requested.clear()
