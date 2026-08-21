"""anyspark.template.patterns — 模式库测试（ExternalLibrary CRUD + 默认库 + 合并）。"""

import tempfile
from pathlib import Path

from anyspark.template.patterns import DEFAULT_TEMPLATES, ExternalLibrary, Template, default_library


def test_template_to_dict_roundtrip() -> None:
    t = Template(
        name="测试模式",
        description="一个测试模板",
        granularity="章",
        position="开局",
        function="悬念",
        params=["a", "b"],
    )
    d = t.to_dict()
    assert d["name"] == "测试模式"
    assert d["granularity"] == "章"
    assert d["position"] == "开局"
    assert d["function"] == "悬念"
    assert d["params"] == ["a", "b"]
    assert d["layer"] == "default"


def test_default_library_returns_copy() -> None:
    """default_library 返回副本——修改不影响全局默认库。"""
    lib1 = default_library()
    lib2 = default_library()
    assert len(lib1) == len(DEFAULT_TEMPLATES)
    assert len(lib1) >= 5
    # 修改副本不影响默认库
    lib1[0].name = "改过的名字"
    assert lib2[0].name != "改过的名字"


def test_default_library_valid_metadata() -> None:
    """默认库元数据合法（granularity/position/function 均在枚举内）。"""
    for t in default_library():
        assert t.granularity in ("全书", "卷", "章", "场景", "段落")
        assert t.position in ("开局", "发展", "高潮", "结局")
        assert t.function in ("铺垫", "主线", "悬念", "爽点", "情感")
        assert t.description  # 非空
        assert t.layer == "default"


def test_external_library_crud() -> None:
    lib = ExternalLibrary(Path(tempfile.mkdtemp()) / "test.db")
    try:
        # 导入一个外部模板
        t = lib.import_template(
            name="自定义·时间循环",
            description="主角反复经历同一天，通过细节差异解开谜题",
            granularity="章",
            position="发展",
            function="悬念",
            params=["循环触发条件", "解谜线索"],
        )
        assert t.layer == "external"
        assert t.name == "自定义·时间循环"

        # 列表
        exts = lib.list_external()
        assert len(exts) == 1
        assert exts[0].name == "自定义·时间循环"
        assert exts[0].params == ["循环触发条件", "解谜线索"]

        # 合并 L2 + L3
        all_templates = lib.all()
        assert len(all_templates) == len(default_library()) + 1
        assert all_templates[-1].layer == "external"  # 外部在末尾
        assert all_templates[0].layer == "default"  # 默认在前

        # 删除
        lib.delete("自定义·时间循环")
        assert lib.list_external() == []
        # 默认库不受影响
        assert len(lib.all()) == len(default_library())
    finally:
        lib.close()


def test_external_library_import_replaces_by_name() -> None:
    """同 name 再导入 = 覆盖（INSERT OR REPLACE）。"""
    lib = ExternalLibrary(Path(tempfile.mkdtemp()) / "test.db")
    try:
        lib.import_template("同名", "旧描述")
        lib.import_template("同名", "新描述")
        exts = lib.list_external()
        assert len(exts) == 1  # 不会变两条
        assert exts[0].description == "新描述"
    finally:
        lib.close()


def test_external_library_delete_nonexistent_is_noop() -> None:
    """删不存在的模板 = 无操作（不报错）。"""
    lib = ExternalLibrary(Path(tempfile.mkdtemp()) / "test.db")
    try:
        lib.delete("不存在的模板")  # 不抛
        assert lib.list_external() == []
    finally:
        lib.close()
