# -*- coding: utf-8 -*-
"""Fail early only when a request genuinely requires Gemini."""
from __future__ import annotations

import os


def install_gemini_availability_contract(core_module) -> None:
    if getattr(core_module.app.state, "gemini_availability_contract_v1", False):
        return

    original_enforce = core_module._enforce_gemini_cooldown

    def enforce_gemini_available() -> None:
        original_enforce()
        if not str(os.environ.get("GEMINI_API_KEY") or "").strip():
            raise core_module.HTTPException(
                status_code=503,
                detail=(
                    "Nguồn dữ liệu này cần Gemini để nhận diện mapping nhưng server chưa cấu hình "
                    "GEMINI_API_KEY. Hãy dùng mapping chuẩn/đã lưu hoặc cấu hình API key."
                ),
            )

    core_module._enforce_gemini_cooldown = enforce_gemini_available
    core_module.app.state.gemini_availability_contract_v1 = True
