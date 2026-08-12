# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from data.json_store import json_store

router = APIRouter(tags=["plot-norms"])


class PlotNormCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    rules: list[str] = Field(default_factory=list, max_length=20)
    avoid: list[str] = Field(default_factory=list, max_length=20)
    active: bool = True


class PlotNormUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    rules: list[str] | None = Field(default=None, max_length=20)
    avoid: list[str] | None = Field(default=None, max_length=20)
    active: bool | None = None


@router.get("/books/{book_id}/plot-norms")
def list_plot_norms(book_id: str):
    return {"norms": json_store.load_plot_norms(book_id)}


@router.post("/books/{book_id}/plot-norms")
def create_plot_norm(book_id: str, data: PlotNormCreate):
    return json_store.add_plot_norm(book_id, data.model_dump())


@router.put("/books/{book_id}/plot-norms/{norm_id}")
def update_plot_norm(book_id: str, norm_id: str, data: PlotNormUpdate):
    try:
        return json_store.update_plot_norm(book_id, norm_id, data.model_dump(exclude_unset=True))
    except Exception as exc:
        raise HTTPException(404, str(exc))


@router.delete("/books/{book_id}/plot-norms/{norm_id}")
def delete_plot_norm(book_id: str, norm_id: str):
    if not json_store.delete_plot_norm(book_id, norm_id):
        raise HTTPException(404, "剧情规范不存在")
    return {"ok": True}

