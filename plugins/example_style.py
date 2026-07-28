"""示例插件：自定义文风约束。

展示如何通过插件系统修改写作行为。
放置在 plugins/ 目录下的 .py 文件会被自动发现和加载。
"""

PLUGIN_NAME = "example_style"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "示例：为写作添加文风约束"
PLUGIN_AUTHOR = ""


def modify_system_prompt(value: str, **kwargs) -> str:
    """在 system prompt 末尾添加文风提示。"""
    style_hint = "\n\n[插件文风约束] 写作时注意：句式简洁有力，多用短句，避免过度修饰。"
    return value + style_hint


def on_write_before(instruction: str = "", **kwargs) -> None:
    """写作前的钩子，可用于日志记录或参数修改。"""
    pass


def on_chapter_save(title: str = "", content: str = "", **kwargs) -> None:
    """章节保存后的钩子。"""
    pass
