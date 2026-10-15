# -*- coding: utf-8 -*-
"""ITEMID-first recognition hardening for physical Pharmacity tags.

Company shelf tags visibly print an ITEMID such as ``P03845``. Treat that printed
identifier as the primary identity signal. Barcode remains supporting evidence.
This layer never changes CTKM business rules; it only hardens OCR observations
before deterministic comparison.
"""
from __future__ import annotations

import re

_ITEMID_PATTERN = re.compile(r"(?<![A-Z0-9])P\s*[-_.:]?\s*(\d{3,8})(?!\d)", re.IGNORECASE)

_HOMOGLYPH_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])P\s*[-_.:]?\s*([A-Za-z0-9|]{4,7})(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_HOMOGLYPH_PREFIX_RE = re.compile(
    r"^\s*[*#]?\s*P\s*[-_.:]?\s*([A-Za-z0-9|]+)\s*[*#]?\s*$",
    re.IGNORECASE,
)

_HOMOGLYPH_DIGIT_MAP = {
    "O": "0", "o": "0",
    "D": "0", "d": "0",
    "Q": "0", "q": "0",
    "I": "1", "i": "1",
    "L": "1", "l": "1",
    "|": "1",
    "Z": "2", "z": "2",
    "S": "5", "s": "5",
    "G": "6", "g": "6",
    "B": "8", "b": "8",
}

_DISALLOWED_P_WORDS = {
    "PRICE", "PROMO", "POSM", "PACK", "PART", "PAGE", "PASS", "PAID",
    "PLUS", "POST", "POOLS", "PRINT", "PHOTO", "PHARMA", "POINT",
    "PIECE", "PIECES", "PCS", "PRODUCT", "PROMOTION", "PROGRAM",
    "POLICY", "POWER", "PANEL", "PILL", "PILLS", "POLLS", "PODS",
    "PIGS", "PLOD", "PLUG", "SLUG", "BILL", "BILLS", "TOTAL",
    "TIEN", "DONG", "VND", "ITEM", "SKU", "PHIEU", "PHAN", "PHI",
}


def recover_homoglyph_sku(raw_token: str) -> str | None:
    """Recover a Pxxxxx SKU with homoglyph confusion (e.g. P3O766 -> P30766).

    Guards:
    - Starts with P/p.
    - Body length between 4 and 7 characters.
    - Must not match common English/Vietnamese shelf words (PRICE, PROMO, etc.).
    - Must contain at least one native ASCII digit, or strictly pass word rejection.
    """
    if not raw_token:
        return None
    raw_str = str(raw_token).strip()
    match = _HOMOGLYPH_PREFIX_RE.match(raw_str)
    if not match:
        return None
    raw_body = match.group(1)
    if not (4 <= len(raw_body) <= 7):
        return None

    clean_upper = re.sub(r"[\s*#_-]", "", raw_str).upper()
    body_upper = raw_body.upper()
    if clean_upper in _DISALLOWED_P_WORDS or body_upper in _DISALLOWED_P_WORDS:
        return None

    has_ascii_digit = any(c.isdigit() for c in raw_body)
    if not has_ascii_digit and (clean_upper in _DISALLOWED_P_WORDS or body_upper in _DISALLOWED_P_WORDS):
        return None

    mapped_chars: list[str] = []
    for c in raw_body:
        if c.isdigit():
            mapped_chars.append(c)
        elif c in _HOMOGLYPH_DIGIT_MAP:
            mapped_chars.append(_HOMOGLYPH_DIGIT_MAP[c])
        else:
            return None

    mapped_body = "".join(mapped_chars)
    if not (4 <= len(mapped_body) <= 7) or not mapped_body.isdigit():
        return None
    return f"P{mapped_body}"


def extract_itemid_candidates(*values) -> list[str]:
    """Return unique canonical P-number candidates in first-seen order.

    Includes both exact numeric P-numbers and safe homoglyph-recovered SKUs.
    """
    found: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value)
        # 1. Exact numeric P-numbers (e.g. P03845, P20383)
        for match in _ITEMID_PATTERN.finditer(text):
            candidate = f"P{match.group(1)}"
            if candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
        # 2. Homoglyph-recovered P-numbers (e.g. P3O766 -> P30766)
        for match in _HOMOGLYPH_TOKEN_PATTERN.finditer(text):
            recovered = recover_homoglyph_sku(match.group(0))
            if recovered and recovered not in seen:
                seen.add(recovered)
                found.append(recovered)
    return found


def _normalize_price(val) -> int | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return int(round(float(val)))
    digits = re.sub(r"\D", "", str(val))
    return int(digits) if digits else None


def _match_price(observed_val, expected_val) -> bool:
    obs = _normalize_price(observed_val)
    if obs is None:
        return False
    if isinstance(expected_val, (list, tuple, set)):
        return any(_normalize_price(e) == obs for e in expected_val)
    exp = _normalize_price(expected_val)
    return exp is not None and obs == exp


def resolve_context_aware_itemid(
    observed_candidates: list[str] | set[str] | tuple[str, ...],
    known_item_ids: list[str] | set[str] | tuple[str, ...],
    observed_price=None,
    item_price_map: dict | None = None,
) -> list[str]:
    """Resolve an OCR misread against active store SKUs using context & price.

    Rules:
    a. If candidates already contain a known SKU -> keep as-is.
    b. If exactly 1 candidate is NOT in known_item_ids, search for SKUs with
       same length and Hamming distance == 1.
    c. Fail-Safe Gate: Only resolve if EXACTLY ONE SKU matches AND promo price
       matches. Otherwise, keep original candidate(s).
    """
    candidates = [str(c).strip().upper() for c in (observed_candidates or []) if str(c).strip()]
    if not candidates:
        return []

    known_set = {str(k).strip().upper() for k in (known_item_ids or []) if str(k).strip()}
    if not known_set:
        return list(candidates)

    # Rule (a): if any candidate is already in known_set, keep as-is
    if any(c in known_set for c in candidates):
        return list(candidates)

    # Rule (b): only attempt recovery if there is exactly 1 candidate
    if len(candidates) != 1:
        return list(candidates)

    cand = candidates[0]
    # Find matching SKUs with same length and Hamming distance == 1
    matches = [
        k for k in known_set
        if len(k) == len(cand) and sum(1 for c1, c2 in zip(cand, k) if c1 != c2) == 1
    ]

    # Rule (c): Fail-Safe Gate
    if len(matches) != 1:
        return list(candidates)

    resolved_sku = matches[0]

    # Price validation gate (if price context is provided)
    if observed_price is not None and str(observed_price).strip() != "" and item_price_map is not None:
        expected_prices = item_price_map.get(resolved_sku)
        if expected_prices is not None:
            if not _match_price(observed_price, expected_prices):
                return list(candidates)

    return [resolved_sku]


def install_tag_audit_itemid_contract(tag_audit_module) -> None:
    if getattr(tag_audit_module, "_itemid_primary_contract_v1", False):
        return

    original_extract = tag_audit_module._extract_tag_with_gemini
    original_compare = tag_audit_module.compare_observation

    def extract_with_itemid_primary(image: bytes, mime_type: str, month: str | None) -> dict:
        observed = original_extract(image, mime_type, month)
        candidates = extract_itemid_candidates(
            observed.get("item_id"),
            observed.get("raw_text"),
            observed.get("date_text"),
            observed.get("product_name"),
            observed.get("promo_text"),
        )
        observed["item_id_candidates"] = candidates
        if len(candidates) == 1:
            observed["item_id"] = candidates[0]
        elif len(candidates) > 1:
            # Never let an OCR guess choose among multiple printed P-numbers.
            observed["item_id"] = ""
        return observed

    def compare_with_itemid_primary(rows: list[dict], observed: dict, manual_item_id: str = "") -> dict:
        if not str(manual_item_id or "").strip():
            candidates = list(observed.get("item_id_candidates") or [])
            if not candidates and observed.get("item_id"):
                candidates = [str(observed["item_id"])]

            known_ids = {str(r.get("item_id") or "").strip().upper() for r in rows if r.get("item_id")}
            item_price_map: dict[str, list] = {}
            for r in rows:
                k = str(r.get("item_id") or "").strip().upper()
                p = r.get("promo_price")
                if k and p is not None:
                    item_price_map.setdefault(k, []).append(p)

            resolved_candidates = resolve_context_aware_itemid(
                candidates,
                known_ids,
                observed_price=observed.get("promo_price"),
                item_price_map=item_price_map,
            )
            if resolved_candidates != candidates:
                observed["item_id_candidates"] = resolved_candidates
                if len(resolved_candidates) == 1:
                    observed["item_id"] = resolved_candidates[0]
                    observed["item_id_resolved_from_context"] = candidates[0]
                candidates = resolved_candidates

            if len(candidates) > 1:
                return {
                    "verdict": {
                        "code": "review_itemid_ambiguous",
                        "title": "Cần xác nhận mã sản phẩm",
                        "detail": "Ảnh đọc được nhiều mã Pxxxxx khác nhau; hệ thống không tự chọn một mã.",
                        "severity": "warning",
                    },
                    "identity_source": "ocr_item_id_ambiguous",
                    "observed": observed,
                    "expected": None,
                    "mismatches": ["item_id"],
                }
        return original_compare(rows, observed, manual_item_id=manual_item_id)

    tag_audit_module._extract_tag_with_gemini = extract_with_itemid_primary
    tag_audit_module.compare_observation = compare_with_itemid_primary
    tag_audit_module.extract_itemid_candidates = extract_itemid_candidates
    tag_audit_module.recover_homoglyph_sku = recover_homoglyph_sku
    tag_audit_module.resolve_context_aware_itemid = resolve_context_aware_itemid
    tag_audit_module._itemid_primary_contract_v1 = True
