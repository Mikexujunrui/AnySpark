# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Pydantic-based tool input validation layer.

Replaces the manual if/elif type-checking in ``tools.validate_tool_input``
with schema-driven Pydantic model generation.  Each tool's ``parameters``
dict is compiled into a Pydantic model at first use, then cached for reuse.
Supports all types used by the existing dict schema (string, boolean, number,
integer, array, enum) and is a drop-in replacement returning the same
``(validated, errors)`` tuple.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

# Cache: parameter-schema JSON fingerprint -> Pydantic model class
_MODEL_CACHE: dict[str, type[BaseModel]] = {}


def _schema_fingerprint(schema: dict[str, Any]) -> str:
    """Return a deterministic JSON fingerprint for a parameter schema dict."""
    return json.dumps(schema, sort_keys=True, ensure_ascii=False, default=str)


def _build_pydantic_model(
    params_schema: dict[str, Any],
) -> type[BaseModel]:
    """Dynamically create a Pydantic model from a tool's parameter dict schema.

    Each entry in *params_schema* is a dict with keys:
        ``type`` (str)   — one of string / boolean / number / integer / array / object
        ``description``  — human-readable description (used as field doc)
        ``required``     — bool, defaults to ``True``
        ``enum``         — optional list of allowed values
        ``items``        — for array/object types, optional sub-schema

    Returns a ``pydantic.BaseModel`` subclass with all fields optional
    (required-ness is checked separately via the ``required`` key).
    """
    fields: dict[str, tuple[type, Any]] = {}

    for key, spec in params_schema.items():
        if not isinstance(spec, dict):
            # Bare string description — treat as optional string
            fields[key] = (str | None, Field(default=None, description=str(spec)))
            continue

        ptype = spec.get("type", "string")
        required = spec.get("required", True)
        description = spec.get("description", "")
        enum_values = spec.get("enum")
        items_schema = spec.get("items")

        python_type = _resolve_python_type(ptype, items_schema, enum_values)

        if required:
            fields[key] = (python_type, Field(..., description=description))
        else:
            fields[key] = (python_type | None, Field(default=None, description=description))

    model_name = f"ToolParams_{len(_MODEL_CACHE)}"
    return create_model(model_name, **fields)  # type: ignore[arg-type]


def _resolve_python_type(
    ptype: str,
    items_schema: dict[str, Any] | None = None,
    enum_values: list[Any] | None = None,
) -> type:
    """Map a parameter type string to a Python type for Pydantic fields."""
    if enum_values:
        from typing import Literal
        str_vals = [str(v) for v in enum_values]
        return Literal[tuple(str_vals)]  # type: ignore[return-value]

    mapping = {
        "string": str,
        "boolean": bool,
        "number": float,
        "integer": int,
        "array": list,
        "object": dict,
    }
    py_type = mapping.get(ptype, str)

    if ptype == "array" and items_schema:
        item_type = _resolve_python_type(items_schema.get("type", "string"))
        return list[item_type]  # type: ignore[return-value]

    return py_type


def validate_with_pydantic(
    tool_name: str,
    params_schema: dict[str, Any],
    args: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Validate *args* against *params_schema* using a dynamically-generated
    Pydantic model.

    Returns ``(validated_dict, errors_list)`` — identical signature and contract
    to ``tools.validate_tool_input`` so it can be used as a drop-in replacement.
    """
    if not params_schema:
        # No parameters defined — accept any input
        return args, []

    fingerprint = _schema_fingerprint(params_schema)
    model_cls = _MODEL_CACHE.get(fingerprint)
    if model_cls is None:
        try:
            model_cls = _build_pydantic_model(params_schema)
            _MODEL_CACHE[fingerprint] = model_cls
        except Exception as exc:
            logger.warning(
                "Failed to build Pydantic model for tool %r (falling back): %s",
                tool_name,
                exc,
            )
            return _fallback_validate(params_schema, args)

    # Pydantic validation: accept extra fields silently (matching original
    # behaviour where unspecified fields pass through).
    try:
        model = model_cls(**args)
    except Exception as exc:
        errors = _extract_pydantic_errors(exc)
        # On validation failure, filter args through a best-effort pass
        validated = {k: v for k, v in args.items() if k in params_schema}
        return validated, errors

    validated = model.model_dump(exclude_unset=True)

    # Merge back any input fields not declared in the schema (preserve extras)
    for k, v in args.items():
        if k not in validated and k not in params_schema:
            validated[k] = v

    # Check required fields that Pydantic might have missed
    errors: list[str] = []
    for key, spec in params_schema.items():
        if isinstance(spec, dict) and spec.get("required", True):
            if key not in args or args[key] is None:
                errors.append(f"Missing required parameter: {key}")

    return validated, errors


def _extract_pydantic_errors(exc: Exception) -> list[str]:
    """Extract user-friendly error messages from a Pydantic validation exception."""
    try:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            msgs: list[str] = []
            for e in exc.errors():
                loc = " → ".join(str(part) for part in e.get("loc", ()))
                msg = e.get("msg", "")
                if loc:
                    msgs.append(f"{loc}: {msg}")
                else:
                    msgs.append(msg)
            return msgs
    except ImportError:
        pass
    return [str(exc)[:200]]


def _fallback_validate(
    params_schema: dict[str, Any],
    args: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Fallback validation when dynamic model creation fails — preserves
    the existing basic type coercion."""
    errors: list[str] = []
    validated: dict[str, Any] = {}

    for key, spec in params_schema.items():
        value = args.get(key)
        if not isinstance(spec, dict):
            if value is not None:
                validated[key] = value
            continue

        expected_type = spec.get("type", "string")
        is_required = spec.get("required", True)

        if value is None or (isinstance(value, str) and not value.strip()):
            if is_required:
                errors.append(f"Missing required parameter: {key}")
            continue

        if expected_type == "string" and not isinstance(value, str):
            validated[key] = str(value)
        elif expected_type == "boolean":
            if isinstance(value, bool):
                validated[key] = value
            elif isinstance(value, str):
                validated[key] = value.lower() in ("true", "1", "yes")
            else:
                validated[key] = bool(value)
        elif expected_type == "number" and not isinstance(value, (int, float)):
            try:
                validated[key] = float(value)
            except (ValueError, TypeError):
                errors.append(f"Parameter {key} must be a number, got {type(value).__name__}")
        elif expected_type == "integer" and not isinstance(value, int):
            try:
                validated[key] = int(value)
            except (ValueError, TypeError):
                errors.append(f"Parameter {key} must be an integer")
        elif expected_type == "array" and not isinstance(value, list):
            if isinstance(value, str):
                try:
                    validated[key] = json.loads(value)
                except json.JSONDecodeError:
                    validated[key] = [value]
            else:
                errors.append(f"Parameter {key} must be an array")
        else:
            enum_values = spec.get("enum")
            if enum_values and value not in enum_values:
                errors.append(f"Parameter {key} must be one of {enum_values}, got '{value}'")
                continue
            validated[key] = value

    for key in args:
        if key not in validated and key not in params_schema:
            validated[key] = args[key]

    return validated, errors
