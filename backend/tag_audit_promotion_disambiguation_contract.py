# -*- coding: utf-8 -*-
"""Promotion disambiguation hardening for the physical shelf-tag scanner.

The core comparator already treats promo price, dates, promo text and product name
as deterministic evidence. ``normal_price`` is also printed on the supported
Pharmacity shelf-tag template and is already validated after a candidate is chosen.
This layer makes that same field participate in candidate selection so two otherwise
indistinguishable promotions cannot be selected by source-row order.
"""
from __future__ import annotations


def install_tag_audit_promotion_disambiguation_contract(tag_audit_module) -> None:
    if getattr(tag_audit_module, "_promotion_disambiguation_contract_v1", False):
        return

    original_business_key = tag_audit_module._row_business_key
    original_score_candidate = tag_audit_module._score_candidate

    def business_key_with_normal_price(row: dict) -> tuple:
        # A different printed old/normal price is a real business distinction.
        # Keep raw source values untouched; parse only for comparison identity.
        return (
            *original_business_key(row),
            tag_audit_module._parse_money(row.get("normal_price")),
        )

    def score_candidate_with_normal_price(row: dict, observed: dict) -> float:
        score = float(original_score_candidate(row, observed))
        observed_normal = tag_audit_module._parse_money(observed.get("normal_price"))
        expected_normal = tag_audit_module._parse_money(row.get("normal_price"))
        if observed_normal is not None and expected_normal is not None:
            # Strong enough to resolve the comparator's 0.75 ambiguity window,
            # but materially weaker than promo price/date evidence.
            score += 1.0 if observed_normal == expected_normal else -1.0
        return score

    tag_audit_module._row_business_key = business_key_with_normal_price
    tag_audit_module._score_candidate = score_candidate_with_normal_price
    tag_audit_module._promotion_disambiguation_contract_v1 = True
