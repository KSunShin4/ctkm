# -*- coding: utf-8 -*-
import json
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

def _load(filename):
    with open(_CONFIG_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)

CANONICAL_SCHEMA = _load("canonical_schema.json")
GEMINI_CONFIG    = _load("gemini_config.json")
GARBAGE_CONFIG   = _load("known_garbage_patterns.json")
SHEET_ROLE_RULES = _load("sheet_role_rules.json")
