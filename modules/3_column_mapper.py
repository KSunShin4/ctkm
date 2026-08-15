# -*- coding: utf-8 -*-
"""
Module 3: AI Column Mapper
============================
Goi Gemini API de map ten cot goc -> canonical field.

Rate limiting cho Gemini FREE TIER (15 req/phut):
  - Token bucket: dam bao khong vuot qua requests_per_minute.
  - Min spacing: khoang cach toi thieu giua 2 lan goi (tranh burst ngan).
  - Exponential backoff + jitter khi nhan 429 Too Many Requests:
      cho base * 2^attempt + random(0, jitter) giay truoc khi thu lai.
  - Sau max_retries_on_429 lan that bai lien tiep -> raise GeminiRateLimitError
    ro rang thay vi crash voi stack trace kho hieu.

Tat ca tham so rate limit doc tu gemini_config.json -> de thay doi khong can
sua code (vd khi nang cap len tra phi, tang requests_per_minute len 60+).
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field as dc_field
from typing import Optional

import requests

from .config_loader import GEMINI_CONFIG, CANONICAL_SCHEMA

# ─── Exceptions ──────────────────────────────────────────────────────────────

class GeminiMappingError(Exception):
    """Loi parse / logic khi xu ly response cua Gemini."""

class GeminiRateLimitError(Exception):
    """429 sau khi retry; chi giu metadata an toan cho UI va log."""

    def __init__(self, message: str, *, category: str = "unknown", retry_after: float = 0,
                 quota: str | None = None, request_id: str | None = None):
        super().__init__(message)
        self.category = category
        self.retry_after = retry_after
        self.quota = quota
        self.request_id = request_id

# ─── Dataclass ket qua ────────────────────────────────────────────────────────

@dataclass
class ColumnMappingResult:
    sheet_name: str
    mapping: dict
    confidence: dict
    unmapped: list = dc_field(default_factory=list)
    low_confidence_fields: list = dc_field(default_factory=list)
    raw_response: Optional[str] = None
    source: str = "gemini"

# ─── Rate Limiter (Token Bucket + Min Spacing) ────────────────────────────────

class _GeminiRateLimiter:
    """
    Thread-safe rate limiter bao gom 2 co che:
    1. Token bucket: gioi han so request trong bat ky cua so 60 giay nao.
    2. Min spacing: dam bao 2 lan goi lien tiep cach nhau it nhat N giay,
       tranh burst ngan ngay ca khi con token.

    Singleton: tat ca luong trong 1 process dung chung 1 instance,
    tranh truong hop 2 sheet duoc xu ly song song cung goi API cung luc.
    """
    _instance: Optional["_GeminiRateLimiter"] = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "_GeminiRateLimiter":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        rl = GEMINI_CONFIG.get("rate_limit", {})
        self._rpm          = rl.get("requests_per_minute", 12)
        self._min_spacing  = rl.get("min_seconds_between_calls", 5)
        self._lock         = threading.Lock()
        self._call_times: deque = deque()  # timestamp cua tung lan goi trong 60s qua
        self._last_call_time: float = 0.0

    def acquire(self) -> None:
        """
        Cho den khi duoc phep goi. Blocking. Thread-safe.
        Goi ham nay TRUOC moi request den Gemini API.
        """
        while True:
            with self._lock:
                now = time.monotonic()

                # Xoa cac timestamp cu hon 60 giay
                cutoff = now - 60.0
                while self._call_times and self._call_times[0] < cutoff:
                    self._call_times.popleft()

                # Kiem tra token bucket
                bucket_ok = len(self._call_times) < self._rpm

                # Kiem tra min spacing
                elapsed_since_last = now - self._last_call_time
                spacing_ok = elapsed_since_last >= self._min_spacing

                if bucket_ok and spacing_ok:
                    self._call_times.append(now)
                    self._last_call_time = now
                    return  # duoc phep goi

                # Tinh thoi gian can cho
                if not bucket_ok:
                    # Cho den khi call cu nhat roi khoi cua so 60s
                    wait_for_bucket = (self._call_times[0] + 60.0) - now
                else:
                    wait_for_bucket = 0.0

                if not spacing_ok:
                    wait_for_spacing = self._min_spacing - elapsed_since_last
                else:
                    wait_for_spacing = 0.0

                wait = max(wait_for_bucket, wait_for_spacing, 0.1)

            # Sleep NGOAI lock de khong block thread khac
            time.sleep(wait)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiMappingError(
            "Khong tim thay GEMINI_API_KEY trong bien moi truong. "
            "Tao file .env voi noi dung: GEMINI_API_KEY=<key>"
        )
    return key

def _field_catalog(schema_section: dict) -> str:
    return "\n".join(
        f"- {name} ({meta.get('type','string')}): {meta.get('desc','')}"
        for name, meta in schema_section.items()
    )

def _sample_values(df, col: str, n: int) -> str:
    """Return the first N non-empty values, preserving their row order."""
    series = df[col].dropna().head(n)
    vals = []
    for value in series:
        text = str(value).strip()
        if text and text not in vals:
            vals.append(text[:120])
    return " | ".join(vals) if vals else "(khong co du lieu mau)"

def _build_prompt(sheet_name: str, df, schema_section: dict, n: int) -> str:
    catalog = _field_catalog(schema_section)
    blocks = "\n".join(
        f'Cot goc: {json.dumps(str(col), ensure_ascii=False)}\n  '
        f'Kieu du lieu: {df[col].dtype}; Ty le rong: {df[col].isna().mean():.0%}; '
        f'Gia tri mau: {_sample_values(df, col, n)}'
        for col in df.columns
    )
    return f"""Day la danh sach canonical field hop le (CHI duoc chon trong danh sach nay):
{catalog}

Sheet dang xu ly: "{sheet_name}"
Danh sach cot goc va TOI DA 5 GIA TRI KHONG RONG DAU TIEN:
{blocks}

QUY TAC NHAN DIEN:
- Phan tich mau gia tri va kieu du lieu de xac dinh y nghia cot; khong chi dua vao ten cot.
- Uu tien bang chung tu gia tri khi ten cot mo ho, trung lap, viet tat hoac sai chinh ta.
- Vi du: P12345 thuong la item_id; ma cua hang nhu SGPMC047 thuong la store_id;
  ngay/thoi gian phai phu hop promo_from/promo_to. Cac cot gia deu la so nen can ket hop
  mau gia tri voi ten cot va quan he gia tri, khong duoc doan chi tu kieu number.
- Neu 5 mau va ten cot van khong du bang chung, chon "__UNMAPPED__" thay vi doan.

Tra ve mot assignment cho MOI cot goc. Moi cot chi duoc gan mot canonical field;
neu khong khop, dung gia tri "__UNMAPPED__". Khong map cac field co auto_filled=true."""

def _response_schema(df, schema_section: dict) -> dict:
    source_columns = [str(col) for col in df.columns]
    canonical_fields = [
        name for name, meta in schema_section.items() if not meta.get("auto_filled", False)
    ]
    return {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_column": {"type": "string", "enum": source_columns},
                        "canonical_field": {
                            "type": "string", "enum": canonical_fields + ["__UNMAPPED__"]
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["source_column", "canonical_field", "confidence"],
                },
            }
        },
        "required": ["assignments"],
    }

def _parse_json(raw: str) -> dict:
    cleaned = raw.strip().strip("`")
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise GeminiMappingError(
            f"Khong parse duoc JSON tu Gemini response: {e}\n"
            f"Raw (500 ky tu dau):\n{raw[:500]}"
        )

# ─── Goi API voi retry + exponential backoff ─────────────────────────────────

def _retry_after_seconds(response) -> float:
    """Read Retry-After/RetryInfo without assuming one response format."""
    raw = response.headers.get("Retry-After", "")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    try:
        details = response.json().get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        return 0.0
    for detail in details if isinstance(details, list) else []:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return max(0.0, float(delay[:-1]))
            except ValueError:
                continue
    return 0.0


def _diagnose_429(response) -> dict[str, str | float | None]:
    """Extract safe quota metadata only; never log API keys or prompts."""
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        error = {}
    message = str(error.get("message", "")).replace("\n", " ").strip()[:300]
    lower = message.lower()
    quota = None
    details = error.get("details", [])
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        for violation in detail.get("violations", []) if isinstance(detail.get("violations", []), list) else []:
            if isinstance(violation, dict):
                quota = violation.get("quotaMetric") or violation.get("quotaId") or quota
    if "per day" in lower or "daily" in lower:
        category = "daily_quota"
    elif "token" in lower:
        category = "token_quota"
    elif "per minute" in lower or "rate limit" in lower or quota:
        category = "rate_quota"
    elif "overload" in lower or "unavailable" in lower:
        category = "service_overload"
    else:
        category = "unknown"
    return {
        "category": category,
        "message": message or "Gemini returned HTTP 429 without details.",
        "quota": str(quota) if quota else None,
        "retry_after": _retry_after_seconds(response),
        "request_id": response.headers.get("x-request-id") or response.headers.get("x-guploader-uploadid"),
    }


def _call_gemini_with_retry(prompt: str, response_schema: dict) -> str:
    """
    Goi Gemini API, tu dong retry khi bi 429 voi exponential backoff + jitter.
    Goi _limiter.acquire() TRUOC moi attempt de tuan thu rate limit chu dong.
    """
    key  = _get_api_key()
    rl   = GEMINI_CONFIG.get("rate_limit", {})
    url  = GEMINI_CONFIG["api_endpoint"].format(model=GEMINI_CONFIG["model"])
    limiter = _GeminiRateLimiter.get()

    max_retries  = rl.get("max_retries_on_429", 4)
    backoff_base = rl.get("backoff_base_seconds", 10)
    backoff_max  = rl.get("backoff_max_seconds", 120)
    jitter       = rl.get("jitter_seconds", 3)
    timeout      = GEMINI_CONFIG.get("timeout_seconds", 30)

    payload = {
        "system_instruction": {
            "parts": [{"text": GEMINI_CONFIG["system_instruction"]}]
        },
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":    GEMINI_CONFIG.get("temperature", 0.0),
            "maxOutputTokens": GEMINI_CONFIG.get("max_output_tokens", 8192),
            # generateContent v1beta currently accepts the legacy structured-output
            # fields below. The newer responseFormat.text.mimeType shape returns
            # HTTP 400 for this endpoint/model even though it is used by newer APIs.
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        },
    }

    last_error = None
    for attempt in range(max_retries + 1):
        # Cho rate limiter cho phep truoc khi gui request
        limiter.acquire()

        try:
            resp = requests.post(
                url,
                headers={"x-goog-api-key": key},
                json=payload,
                timeout=timeout,
            )

            if resp.status_code == 429:
                # Lay retry-after header neu co (Gemini doi khi gui)
                diagnostic = _diagnose_429(resp)
                retry_after = float(diagnostic["retry_after"] or 0)
                wait = max(
                    retry_after,
                    min(backoff_base * (2 ** attempt), backoff_max)
                ) + random.uniform(0, jitter)

                print(
                    "  [RateLimit] Gemini 429 "
                    f"category={diagnostic['category']} quota={diagnostic['quota'] or '-'} "
                    f"retry_after={retry_after:.1f}s request_id={diagnostic['request_id'] or '-'} "
                    f"message={diagnostic['message']}"
                )

                if attempt >= max_retries:
                    raise GeminiRateLimitError(
                        f"Bi 429 Too Many Requests sau {attempt+1} lan thu. "
                        f"Da cho tong cong ~{backoff_base*(2**attempt):.0f}s. "
                        f"Hay cho vai phut roi chay lai, hoac giam so sheet moi "
                        f"Ly do: {diagnostic['message']}",
                        category=str(diagnostic["category"]),
                        retry_after=retry_after,
                        quota=diagnostic["quota"],
                        request_id=diagnostic["request_id"],
                    )

                print(
                    f"  [RateLimit] 429 nhan duoc (attempt {attempt+1}/{max_retries+1}). "
                    f"Cho {wait:.1f}s truoc khi thu lai…"
                )
                time.sleep(wait)
                continue  # thu lai, limiter.acquire() se xu ly spacing

            resp.raise_for_status()

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise GeminiMappingError(f"Gemini tra ve response khong co candidates: {data}")

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason")
            if finish_reason == "MAX_TOKENS":
                raise GeminiMappingError(
                    "Gemini da dung vi het output token truoc khi hoan tat JSON. "
                    "Hay tang max_output_tokens hoac giam so cot trong mot request."
                )
            parts = candidate.get("content", {}).get("parts", [])
            text  = "".join(p.get("text", "") for p in parts).strip()
            if not text:
                raise GeminiMappingError("Gemini tra ve noi dung rong.")

            return text

        except GeminiRateLimitError:
            raise  # khong retry them, da xu ly o tren
        except GeminiMappingError:
            raise  # loi parse/logic, khong retry
        except requests.exceptions.Timeout:
            last_error = f"Timeout sau {timeout}s"
            wait = min(backoff_base * (2 ** attempt), backoff_max) + random.uniform(0, jitter)
            if attempt < max_retries:
                print(f"  [Timeout] attempt {attempt+1}/{max_retries+1}. Cho {wait:.1f}s…")
                time.sleep(wait)
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            wait = min(backoff_base * (2 ** attempt), backoff_max) + random.uniform(0, jitter)
            if attempt < max_retries:
                print(f"  [NetworkError] {e}. Cho {wait:.1f}s…")
                time.sleep(wait)

    raise GeminiMappingError(
        f"Goi Gemini API that bai sau {max_retries+1} lan thu. Loi cuoi: {last_error}"
    )

# ─── Ham chinh ────────────────────────────────────────────────────────────────

def map_columns_with_gemini(
    sheet_name: str,
    df,
    schema_section: dict,
) -> ColumnMappingResult:
    """
    Map ten cot goc -> canonical field bang Gemini.
    schema_section: truyen CANONICAL_SCHEMA["fact_fields"] hoac ["dimension_fields"]
                    hoac ["pog_fields"] tuy theo loai sheet dang xu ly.

    Rate limiting duoc xu ly tu dong qua _GeminiRateLimiter — caller khong can
    tu them sleep() hay logic retry o ben ngoai.
    """
    n = GEMINI_CONFIG.get("sample_rows_per_column", 8)
    prompt = _build_prompt(sheet_name, df, schema_section, n)
    raw    = _call_gemini_with_retry(prompt, _response_schema(df, schema_section))
    parsed = _parse_json(raw)

    source_columns = {str(col) for col in df.columns}
    allowed_fields = {
        name for name, meta in schema_section.items() if not meta.get("auto_filled", False)
    }
    mapping, confidence, unmapped, seen = {}, {}, [], set()
    assignments = parsed.get("assignments")
    if not isinstance(assignments, list):
        raise GeminiMappingError("Gemini response thieu mang assignments hop le.")
    for item in assignments:
        if not isinstance(item, dict):
            raise GeminiMappingError("Gemini response co assignment sai kieu.")
        source = item.get("source_column")
        target = item.get("canonical_field")
        if isinstance(target, str):
            normalized_target = target.strip().strip("*").strip().upper()
            if normalized_target in {"UNMAPPED", "__UNMAPPED__"}:
                target = "__UNMAPPED__"
        try:
            score = float(item.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise GeminiMappingError(f"Confidence khong hop le cho cot {source!r}.") from exc
        if source not in source_columns or source in seen:
            raise GeminiMappingError(f"Cot nguon khong hop le hoac bi lap: {source!r}.")
        if not 0 <= score <= 1:
            raise GeminiMappingError(f"Confidence ngoai khoang 0..1 cho cot {source!r}.")
        seen.add(source)
        confidence[source] = score
        if target == "__UNMAPPED__":
            unmapped.append(source)
        elif target in allowed_fields:
            mapping[source] = target
        else:
            raise GeminiMappingError(f"Canonical field khong hop le: {target!r}.")
    missing = sorted(source_columns - seen)
    if missing:
        raise GeminiMappingError(f"Gemini khong tra assignment cho cac cot: {missing}")
    threshold  = GEMINI_CONFIG.get("confidence_threshold", 0.6)
    low_conf   = [c for c, v in confidence.items() if float(v) < threshold]

    return ColumnMappingResult(
        sheet_name=sheet_name,
        mapping=mapping,
        confidence=confidence,
        unmapped=unmapped,
        low_confidence_fields=low_conf,
        raw_response=raw,
        source="gemini",
    )
