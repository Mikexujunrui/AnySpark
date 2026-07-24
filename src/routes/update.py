# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Update check routes — lets the frontend query GitHub for new releases
and toggle the update-check feature on/off from the settings panel.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from core.settings import get_settings, update_settings
from core.update_checker import check_for_update, get_local_version

router = APIRouter(tags=["update"])


class ToggleUpdateCheck(BaseModel):
    enabled: bool


@router.get("/update/status")
def get_update_status():
    """Return the local version and whether update checking is enabled."""
    s = get_settings()
    return {
        "current_version": get_local_version(),
        "update_check_enabled": s.update_check_enabled,
    }


@router.post("/update/toggle")
def toggle_update_check(data: ToggleUpdateCheck):
    """Enable or disable the update-check feature (persisted to settings)."""
    s = get_settings()
    s.update_check_enabled = data.enabled
    update_settings(s)
    return {"update_check_enabled": s.update_check_enabled}


@router.get("/update/check")
def perform_update_check():
    """Check GitHub for a newer release.

    Honors the ``update_check_enabled`` toggle — when disabled, returns a
    no-op result instead of contacting GitHub.
    """
    s = get_settings()
    if not s.update_check_enabled:
        return {
            "current_version": get_local_version(),
            "update_check_enabled": False,
            "has_update": False,
            "message": "更新检测已关闭",
        }
    result = check_for_update()
    result["update_check_enabled"] = True
    return result
