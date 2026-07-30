from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import desktop_launcher
from core.config import APP_VERSION
from core.desktop_bridge import clear_activation, request_activation, wait_for_activation


def test_desktop_activation_signal_is_consumed_once():
    clear_activation()
    assert wait_for_activation(0) is False
    request_activation()
    assert wait_for_activation(0) is True
    assert wait_for_activation(0) is False


def test_instance_lock_blocks_second_process_handle(tmp_path):
    lock_path = tmp_path / ".anyspark.lock"
    first = desktop_launcher.InstanceLock(lock_path)
    second = desktop_launcher.InstanceLock(lock_path)

    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()

    assert second.acquire() is True
    second.release()


def test_desktop_readiness_requires_matching_version(monkeypatch):
    monkeypatch.setattr(
        desktop_launcher,
        "_health_payload",
        lambda _timeout=0.8: {
            "status": "ok",
            "app": "AnySpark",
            "version": APP_VERSION,
            "desktop_shell": True,
        },
    )
    assert desktop_launcher._is_desktop_server_ready() is True

    monkeypatch.setattr(
        desktop_launcher,
        "_health_payload",
        lambda _timeout=0.8: {"status": "ok", "app": "AnySpark"},
    )
    assert desktop_launcher._is_anyspark_running() is True
    assert desktop_launcher._is_desktop_server_ready() is False


def test_server_health_identifies_desktop_shell():
    from server import health_check

    payload = asyncio.run(health_check())
    assert payload == {
        "status": "ok",
        "app": "AnySpark",
        "version": APP_VERSION,
        "desktop_shell": True,
    }


def test_desktop_activate_endpoint_sets_signal():
    from server import desktop_activate

    clear_activation()
    assert asyncio.run(desktop_activate()) == {"status": "ok"}
    assert wait_for_activation(0) is True


def test_controller_shutdown_stops_server_and_joins_thread():
    class FakeServer:
        should_exit = False

    class FakeThread:
        joined = False

        @staticmethod
        def is_alive():
            return True

        def join(self, timeout):
            assert timeout == 8
            self.joined = True

    controller = desktop_launcher.DesktopController()
    controller.server = FakeServer()
    thread = FakeThread()
    controller.server_thread = thread

    controller.shutdown()

    assert controller.server.should_exit is True
    assert thread.joined is True
