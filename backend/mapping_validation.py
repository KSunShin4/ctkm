# -*- coding: utf-8 -*-
"""Backend compatibility facade for the shared pipeline mapping validator.

Single Source of Truth (SSOT): modules/mapping_validation.py
This module preserves backward compatibility for existing imports from backend.mapping_validation.
"""
from modules.mapping_validation import (  # noqa: F401
    MULTI_SOURCE_CANONICAL_FIELDS,
    validate_manual_mapping,
)

__all__ = ["MULTI_SOURCE_CANONICAL_FIELDS", "validate_manual_mapping"]
