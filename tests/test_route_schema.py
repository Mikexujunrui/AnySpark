"""API schema regressions discovered during packaged-app smoke tests."""


def test_openapi_operation_ids_are_unique(monkeypatch, tmp_path):
    monkeypatch.setenv("ANYSPARK_HOME", str(tmp_path / "anyspark-home"))

    from server import app

    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
