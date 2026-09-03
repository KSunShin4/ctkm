# -*- coding: utf-8 -*-
"""Backend compatibility import for the shared pipeline mapping validator."""
from modules.mapping_validation import (  # noqa: F401
    MULTI_SOURCE_CANONICAL_FIELDS,
    validate_manual_mapping,
)

__all__ = ["MULTI_SOURCE_CANONICAL_FIELDS", "validate_manual_mapping"]
