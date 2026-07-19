import importlib.util
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT

logger = logging.getLogger(__name__)

PLUGINS_DIR = PROJECT_ROOT / "plugins"


@dataclass
class PluginMeta:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""


@dataclass
class Plugin:
    meta: PluginMeta
    module: Any = None
    hooks: dict[str, Callable] = field(default_factory=dict)
    custom_tools: list[dict] = field(default_factory=list)
    enabled: bool = True


HOOK_NAMES = [
    "on_extract_before",
    "on_extract_after",
    "on_write_before",
    "on_write_after",
    "on_tool_before",
    "on_tool_after",
    "on_chat_message",
    "on_knowledge_update",
    "on_chapter_save",
    "on_session_start",
    "on_session_end",
    "modify_system_prompt",
]


class PluginManager:
    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._hook_cache: dict[str, list[Callable]] = {}

    def discover(self):
        if not PLUGINS_DIR.exists():
            return

        for path in PLUGINS_DIR.iterdir():
            if path.suffix == ".py" and not path.name.startswith("_"):
                self._load_file(path)
            elif path.is_dir() and (path / "__init__.py").exists():
                self._load_file(path / "__init__.py")

    def _load_file(self, path: Path):
        module_name = f"plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(path))
            if spec is None or spec.loader is None:
                logger.warning("Cannot load plugin %s: unable to create module spec", path)
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            meta = PluginMeta(
                name=getattr(module, "PLUGIN_NAME", path.stem),
                version=getattr(module, "PLUGIN_VERSION", "0.1.0"),
                description=getattr(module, "PLUGIN_DESCRIPTION", ""),
                author=getattr(module, "PLUGIN_AUTHOR", ""),
            )

            hooks = {}
            for hook_name in HOOK_NAMES:
                fn = getattr(module, hook_name, None)
                if callable(fn):
                    hooks[hook_name] = fn

            custom_tools = getattr(module, "CUSTOM_TOOLS", [])

            plugin = Plugin(meta=meta, module=module, hooks=hooks, custom_tools=custom_tools)
            self._plugins[meta.name] = plugin
            self._rebuild_hook_cache()
        except Exception as e:
            print(f"[Plugin] 加载失败 {path.name}: {e}")

    def _rebuild_hook_cache(self):
        self._hook_cache.clear()
        for plugin in self._plugins.values():
            if not plugin.enabled:
                continue
            for hook_name, fn in plugin.hooks.items():
                self._hook_cache.setdefault(hook_name, []).append(fn)

    def call_hook(self, hook_name: str, **kwargs) -> list[Any]:
        results = []
        for fn in self._hook_cache.get(hook_name, []):
            try:
                result = fn(**kwargs)
                results.append(result)
            except Exception:
                pass
        return results

    def call_hook_chain(self, hook_name: str, value: Any, **kwargs) -> Any:
        for fn in self._hook_cache.get(hook_name, []):
            try:
                result = fn(value=value, **kwargs)
                if result is not None:
                    value = result
            except Exception:
                pass
        return value

    def get_custom_tools(self) -> list[dict]:
        tools = []
        for plugin in self._plugins.values():
            if plugin.enabled:
                tools.extend(plugin.custom_tools)
        return tools

    def list_plugins(self) -> list[dict]:
        return [{
            "name": p.meta.name,
            "version": p.meta.version,
            "description": p.meta.description,
            "enabled": p.enabled,
            "hooks": list(p.hooks.keys()),
            "tools": len(p.custom_tools),
        } for p in self._plugins.values()]

    def enable(self, name: str) -> bool:
        if name in self._plugins:
            self._plugins[name].enabled = True
            self._rebuild_hook_cache()
            return True
        return False

    def disable(self, name: str) -> bool:
        if name in self._plugins:
            self._plugins[name].enabled = False
            self._rebuild_hook_cache()
            return True
        return False


plugin_manager = PluginManager()
plugin_manager.discover()
