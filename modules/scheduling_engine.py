# -*- coding: utf-8 -*-
"""Constraint-based weekly staff scheduling for the store scheduling module."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

from ortools.sat.python import cp_model


REQUEST_TYPES = {
    "OFF",
    "MUST_MORNING",
    "MUST_AFTERNOON",
    "PREFER_MORNING",
    "PREFER_AFTERNOON",
}
SHIFTS = {"MORNING", "AFTERNOON", "OFF"}
LEVELS = {"HARD", "SOFT"}
RELATION_TYPES = {"UNLIMITED", "MAX", "MIN", "EXACT", "NEVER", "PREFER_TOGETHER", "PREFER_APART"}
RECEIVING_RELATIONS = {"NORMAL", "PREFER_TOGETHER", "AVOID", "NEVER"}
EMPLOYEE_ROLES = {"STORE_MANAGER", "EMPLOYEE"}
DEFAULT_MANAGER_TREND = [
    {"weekday": 0, "morning": 57, "afternoon": 66},
    {"weekday": 1, "morning": 42, "afternoon": 83},
    {"weekday": 2, "morning": 57, "afternoon": 65},
    {"weekday": 3, "morning": 56, "afternoon": 51},
    {"weekday": 4, "morning": 53, "afternoon": 59},
    {"weekday": 5, "morning": 48, "afternoon": 69},
    {"weekday": 6, "morning": 63, "afternoon": 73},
]
REGIONAL_MANAGER_RULES = (
    {"weekday": 0, "shift": "MORNING", "level": "HARD", "source": "REGIONAL"},
    {"weekday": 1, "shift": "AFTERNOON", "level": "HARD", "source": "REGIONAL"},
)
VARIANT_WEIGHTS = {
    "balanced": {
        "shortage": 1200,
        "shift_target": 90,
        "receiving_target": 45,
        "switch": 28,
        "preference": 32,
        "fairness": 16,
        "pairing": 30,
        "off_receiving_compensation": 160,
        "manager_shift_target": 500,
        "manager_trend": 10,
    },
    "stable": {
        "shortage": 1200,
        "shift_target": 75,
        "receiving_target": 40,
        "switch": 85,
        "preference": 25,
        "fairness": 18,
        "pairing": 25,
        "off_receiving_compensation": 160,
        "manager_shift_target": 500,
        "manager_trend": 10,
    },
    "preferences": {
        "shortage": 1200,
        "shift_target": 80,
        "receiving_target": 40,
        "switch": 24,
        "preference": 95,
        "fairness": 14,
        "pairing": 35,
        "off_receiving_compensation": 160,
        "manager_shift_target": 500,
        "manager_trend": 10,
    },
}
VARIANT_LABELS = {
    "balanced": "Cân bằng tổng thể",
    "stable": "Ít đổi ca hơn",
    "preferences": "Ưu tiên nguyện vọng",
}


class SchedulingError(ValueError):
    pass


def _parse_date(value: Any, field: str = "date") -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise SchedulingError(f"{field} phải có dạng YYYY-MM-DD") from exc


def _as_int(value: Any, *, field: str, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise SchedulingError(f"{field} phải là số nguyên") from exc
    if result < minimum or (maximum is not None and result > maximum):
        suffix = f"..{maximum}" if maximum is not None else f">={minimum}"
        raise SchedulingError(f"{field} phải nằm trong {minimum}{suffix}")
    return result


def _week_dates(week_start: date) -> list[date]:
    return [week_start + timedelta(days=offset) for offset in range(7)]


def _normalize_employee(raw: dict[str, Any], position: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SchedulingError(f"employees[{position}] không hợp lệ")
    employee_id = str(raw.get("id") or "").strip()
    if not employee_id:
        raise SchedulingError(f"employees[{position}].id không được trống")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SchedulingError(f"employees[{position}].name không được trống")
    code = raw.get("staff_code", "")
    if not isinstance(code, str):
        code = str(code)
    role = str(raw.get("role") or "EMPLOYEE").strip().upper()
    if role not in EMPLOYEE_ROLES:
        raise SchedulingError(f"employees[{position}].role không hợp lệ")
    return {
        "id": employee_id,
        "name": name,
        "staff_code": code,
        "role": role,
        "active": bool(raw.get("active", True)),
    }


def normalize_config(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SchedulingError("Payload xếp lịch phải là object")
    week_start = _parse_date(payload.get("week_start"), "week_start")
    if week_start.weekday() != 0:
        raise SchedulingError("week_start phải là Thứ 2")
    days = _week_dates(week_start)
    day_keys = {item.isoformat() for item in days}

    employees = [_normalize_employee(raw, i) for i, raw in enumerate(payload.get("employees") or [])]
    active = [item for item in employees if item["active"]]
    if not active:
        raise SchedulingError("Cần ít nhất 1 nhân viên đang hoạt động")
    active_managers = [item for item in active if item["role"] == "STORE_MANAGER"]
    if len(active_managers) != 1:
        raise SchedulingError("Phải có đúng 1 CHT đang hoạt động")
    manager_id = active_managers[0]["id"]
    ids = [item["id"] for item in active]
    if len(ids) != len(set(ids)):
        raise SchedulingError("employee.id phải duy nhất")
    employee_ids = set(ids)

    staffing_input = payload.get("staffing") or []
    staffing_by_date: dict[str, dict[str, int]] = {}
    for raw in staffing_input:
        if not isinstance(raw, dict):
            raise SchedulingError("staffing chứa phần tử không hợp lệ")
        key = _parse_date(raw.get("date"), "staffing.date").isoformat()
        if key not in day_keys:
            raise SchedulingError(f"staffing.date {key} nằm ngoài tuần")
        morning = _as_int(raw.get("morning", 0), field=f"staffing[{key}].morning", maximum=3)
        afternoon = _as_int(raw.get("afternoon", 0), field=f"staffing[{key}].afternoon", maximum=3)
        if morning + afternoon > len(active):
            # A shortage is allowed when OFF makes the target unreachable, but the
            # configured nominal target itself must still be physically meaningful.
            raise SchedulingError(f"Nhu cầu {key} vượt số nhân viên đang hoạt động")
        staffing_by_date[key] = {"morning": morning, "afternoon": afternoon}
    for item in days:
        key = item.isoformat()
        if key not in staffing_by_date:
            staffing_by_date[key] = {"morning": 3 if item.weekday() == 0 else 2, "afternoon": 2 if item.weekday() == 0 else 3}

    requests = []
    seen_hard: dict[tuple[str, str], str] = {}
    for position, raw in enumerate(payload.get("requests") or []):
        if not isinstance(raw, dict):
            raise SchedulingError(f"requests[{position}] không hợp lệ")
        employee_id = str(raw.get("employee_id") or "").strip()
        if employee_id not in employee_ids:
            raise SchedulingError(f"requests[{position}] dùng employee_id không tồn tại")
        key = _parse_date(raw.get("date"), f"requests[{position}].date").isoformat()
        if key not in day_keys:
            raise SchedulingError(f"requests[{position}].date nằm ngoài tuần")
        req_type = str(raw.get("type") or "").strip().upper()
        if req_type not in REQUEST_TYPES:
            raise SchedulingError(f"requests[{position}].type không hợp lệ")
        if req_type in {"OFF", "MUST_MORNING", "MUST_AFTERNOON"}:
            identity = (employee_id, key)
            previous = seen_hard.get(identity)
            if previous and previous != req_type:
                raise SchedulingError(
                    f"Xung đột HARD: {employee_id} ngày {key} vừa {previous} vừa {req_type}"
                )
            seen_hard[identity] = req_type
        requests.append({"employee_id": employee_id, "date": key, "type": req_type})

    fixed_rules = []
    for position, raw in enumerate(payload.get("fixed_weekday_rules") or []):
        if not isinstance(raw, dict):
            raise SchedulingError(f"fixed_weekday_rules[{position}] không hợp lệ")
        employee_id = str(raw.get("employee_id") or "").strip()
        if employee_id not in employee_ids:
            raise SchedulingError(f"fixed_weekday_rules[{position}] dùng employee_id không tồn tại")
        weekday = _as_int(raw.get("weekday"), field="fixed_weekday_rules.weekday", maximum=6)
        shift = str(raw.get("shift") or "").strip().upper()
        if shift not in {"MORNING", "AFTERNOON", "OFF"}:
            raise SchedulingError("fixed_weekday_rules.shift không hợp lệ")
        level = str(raw.get("level") or "HARD").strip().upper()
        if level not in LEVELS:
            raise SchedulingError("fixed_weekday_rules.level không hợp lệ")
        source = str(raw.get("source") or "USER").strip().upper()
        # Legacy default rows are migrated into the canonical regional rules below.
        if source == "REGIONAL":
            continue
        if employee_id == manager_id and level == "HARD" and (
            (weekday == 0 and shift == "MORNING") or
            (weekday == 1 and shift == "AFTERNOON")
        ):
            continue
        fixed_rules.append({
            "employee_id": employee_id,
            "weekday": weekday,
            "shift": shift,
            "level": level,
            "source": "USER",
        })
    for regional in REGIONAL_MANAGER_RULES:
        fixed_rules.append({"employee_id": manager_id, **regional})

    employee_rules: dict[str, dict[str, Any]] = {}
    for raw in payload.get("employee_rules") or []:
        if not isinstance(raw, dict):
            continue
        employee_id = str(raw.get("employee_id") or "").strip()
        if employee_id not in employee_ids:
            raise SchedulingError("employee_rules dùng employee_id không tồn tại")
        def optional_count(name: str, maximum: int = 7):
            value = raw.get(name)
            return None if value in (None, "") else _as_int(value, field=f"employee_rules.{name}", maximum=maximum)
        minimum = optional_count("receiving_min")
        target = optional_count("receiving_target")
        maximum = optional_count("receiving_max")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise SchedulingError("receiving_min không được lớn hơn receiving_max")
        employee_rules[employee_id] = {
            "target_morning": optional_count("target_morning"),
            "target_afternoon": optional_count("target_afternoon"),
            "receiving_min": minimum,
            "receiving_target": target,
            "receiving_max": maximum,
            "off_receiving_compensation": bool(raw.get("off_receiving_compensation", False)),
        }

    receiving_by_date: dict[str, int] = {}
    for raw in payload.get("receiving_days") or []:
        if isinstance(raw, str):
            key = _parse_date(raw, "receiving_days").isoformat()
            count = staffing_by_date.get(key, {}).get("afternoon", 0)
        elif isinstance(raw, dict):
            key = _parse_date(raw.get("date"), "receiving_days.date").isoformat()
            count = _as_int(raw.get("count", staffing_by_date.get(key, {}).get("afternoon", 0)), field="receiving_days.count", maximum=3)
        else:
            raise SchedulingError("receiving_days chứa phần tử không hợp lệ")
        if key not in day_keys:
            raise SchedulingError("receiving_days có ngày nằm ngoài tuần")
        if count > staffing_by_date[key]["afternoon"]:
            raise SchedulingError(
                f"receiving_days {key}: số người nhận hàng ({count}) vượt số người ca Chiều ({staffing_by_date[key]['afternoon']})"
            )
        receiving_by_date[key] = count

    raw_trend = payload.get("manager_trend")
    if not isinstance(raw_trend, dict):
        raw_trend = {}
    trend_enabled = bool(raw_trend.get("enabled", True))
    trend_rows = raw_trend.get("scores")
    if not isinstance(trend_rows, list) or not trend_rows:
        trend_rows = deepcopy(DEFAULT_MANAGER_TREND)
    trend_scores: dict[int, dict[str, int]] = {}
    for raw in trend_rows:
        if not isinstance(raw, dict):
            raise SchedulingError("manager_trend.scores chứa phần tử không hợp lệ")
        weekday = _as_int(raw.get("weekday"), field="manager_trend.weekday", maximum=6)
        morning_score = _as_int(raw.get("morning", 0), field="manager_trend.morning", maximum=10000)
        afternoon_score = _as_int(raw.get("afternoon", 0), field="manager_trend.afternoon", maximum=10000)
        trend_scores[weekday] = {"morning": morning_score, "afternoon": afternoon_score}
    defaults_by_weekday = {item["weekday"]: item for item in DEFAULT_MANAGER_TREND}
    for weekday in range(7):
        default = defaults_by_weekday[weekday]
        trend_scores.setdefault(weekday, {"morning": default["morning"], "afternoon": default["afternoon"]})

    pairings = []
    for position, raw in enumerate(payload.get("pairing_rules") or []):
        if not isinstance(raw, dict):
            raise SchedulingError(f"pairing_rules[{position}] không hợp lệ")
        employee_a = str(raw.get("employee_a") or "").strip()
        employee_b = str(raw.get("employee_b") or "").strip()
        if employee_a not in employee_ids or employee_b not in employee_ids or employee_a == employee_b:
            raise SchedulingError("pairing_rules phải chọn 2 nhân viên khác nhau đang hoạt động")

        legacy_max = raw.get("max_same_shifts_per_week")
        relation_type = str(raw.get("relation_type") or ("MAX" if legacy_max not in (None, "") else "UNLIMITED")).strip().upper()
        if relation_type not in RELATION_TYPES:
            raise SchedulingError("pairing_rules.relation_type không hợp lệ")

        raw_count = raw.get("count", legacy_max)
        count = None if raw_count in (None, "") else _as_int(raw_count, field="pairing_rules.count", maximum=7)
        if relation_type in {"MAX", "MIN", "EXACT", "PREFER_TOGETHER"} and count is None:
            raise SchedulingError(f"pairing_rules loại {relation_type} cần số ca/tuần")
        if relation_type == "NEVER":
            count = 0

        level = str(raw.get("level") or "SOFT").strip().upper()
        if level not in LEVELS:
            raise SchedulingError("pairing_rules.level không hợp lệ")
        if relation_type in {"PREFER_TOGETHER", "PREFER_APART"}:
            level = "SOFT"
        elif relation_type == "NEVER":
            level = "HARD"

        receiving_relation = raw.get("receiving_relation")
        if receiving_relation is None:
            legacy_allowed = bool(raw.get("receiving_day_allowed", True))
            if legacy_allowed:
                receiving_relation = "NORMAL"
            else:
                receiving_relation = "NEVER" if level == "HARD" else "AVOID"
        receiving_relation = str(receiving_relation).strip().upper()
        if receiving_relation not in RECEIVING_RELATIONS:
            raise SchedulingError("pairing_rules.receiving_relation không hợp lệ")

        pairings.append({
            "employee_a": employee_a,
            "employee_b": employee_b,
            "relation_type": relation_type,
            "count": count,
            "level": level,
            "receiving_relation": receiving_relation,
        })

    morning_time_overrides = []
    for raw in payload.get("morning_time_overrides") or []:
        employee_id = str(raw.get("employee_id") or "").strip()
        if employee_id not in employee_ids:
            raise SchedulingError("morning_time_overrides dùng employee_id không tồn tại")
        key = _parse_date(raw.get("date"), "morning_time_overrides.date").isoformat()
        start = str(raw.get("start") or "").strip()
        if start not in {"06:00", "07:00"}:
            raise SchedulingError("morning_time_overrides.start chỉ nhận 06:00 hoặc 07:00")
        morning_time_overrides.append({"employee_id": employee_id, "date": key, "start": start})

    return {
        "week_start": week_start.isoformat(),
        "week_end": days[-1].isoformat(),
        "store_label": str(payload.get("store_label") or "1885"),
        "employees": employees,
        "active_employees": active,
        "staffing": [{"date": key, **staffing_by_date[key]} for key in sorted(staffing_by_date)],
        "staffing_by_date": staffing_by_date,
        "requests": requests,
        "fixed_weekday_rules": fixed_rules,
        "employee_rules": employee_rules,
        "manager_trend": {
            "enabled": trend_enabled,
            "scores": [
                {"weekday": weekday, **trend_scores[weekday]}
                for weekday in range(7)
            ],
        },
        "receiving_by_date": receiving_by_date,
        "pairing_rules": pairings,
        "morning_time_overrides": morning_time_overrides,
    }



def _hard_day_sets(config: dict[str, Any]) -> tuple[dict[str, dict[str, set[str]]], dict[str, int]]:
    """Collect explicit HARD availability/shift requests without inferring OFF from under-filled days."""
    day_keys = [item.isoformat() for item in _week_dates(_parse_date(config["week_start"]))]
    hard_by_day: dict[str, dict[str, set[str]]] = {
        key: {"MORNING": set(), "AFTERNOON": set(), "OFF": set()} for key in day_keys
    }
    start = _parse_date(config["week_start"])
    requests = list(config["requests"])
    for rule in config["fixed_weekday_rules"]:
        if rule["level"] != "HARD":
            continue
        key = (start + timedelta(days=rule["weekday"])).isoformat()
        requests.append({
            "employee_id": rule["employee_id"],
            "date": key,
            "type": {"MORNING": "MUST_MORNING", "AFTERNOON": "MUST_AFTERNOON", "OFF": "OFF"}[rule["shift"]],
        })

    hard_kind = {"MUST_MORNING": "MORNING", "MUST_AFTERNOON": "AFTERNOON", "OFF": "OFF"}
    for request in requests:
        kind = hard_kind.get(request["type"])
        if kind and request["date"] in hard_by_day:
            hard_by_day[request["date"]][kind].add(request["employee_id"])

    off_counts = {item["id"]: 0 for item in config["active_employees"]}
    for day in hard_by_day.values():
        for employee_id in day["OFF"]:
            off_counts[employee_id] = off_counts.get(employee_id, 0) + 1
    return hard_by_day, off_counts


def _effective_staffing_by_date(config: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Rebalance nominal daily staffing when explicit OFF reduces available people.

    Example: nominal 3 morning + 2 afternoon with one OFF becomes 2 + 2,
    while nominal 2 + 3 becomes 2 + 2. The split stays as close as possible
    to the nominal ratio instead of leaving one shift at 3 and the other at 1.
    """
    hard_by_day, _ = _hard_day_sets(config)
    active_count = len(config["active_employees"])
    result: dict[str, dict[str, int]] = {}
    for key, nominal in config["staffing_by_date"].items():
        nominal_morning = int(nominal["morning"])
        nominal_afternoon = int(nominal["afternoon"])
        nominal_total = nominal_morning + nominal_afternoon
        off_count = len(hard_by_day[key]["OFF"])
        available = max(0, active_count - off_count)
        effective_total = min(available, nominal_total)

        candidates = []
        for morning in range(0, min(nominal_morning, effective_total) + 1):
            afternoon = effective_total - morning
            if afternoon < 0 or afternoon > nominal_afternoon:
                continue
            ratio_distance = abs(morning * nominal_total - nominal_morning * effective_total)
            balance_distance = abs(morning - afternoon)
            candidates.append((ratio_distance, balance_distance, morning, afternoon))
        if not candidates:
            effective_morning, effective_afternoon = 0, 0
        else:
            _, _, effective_morning, effective_afternoon = min(candidates)

        result[key] = {
            "morning": effective_morning,
            "afternoon": effective_afternoon,
            "available": available,
            "off_count": off_count,
            "nominal_morning": nominal_morning,
            "nominal_afternoon": nominal_afternoon,
        }
    return result


def _hard_precheck(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    hard_by_day, _ = _hard_day_sets(config)
    effective_staffing = _effective_staffing_by_date(config)
    employee_names = {item["id"]: item["name"] for item in config["active_employees"]}

    by_employee_day: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, people in hard_by_day.items():
        for kind in ("MORNING", "AFTERNOON", "OFF"):
            for employee_id in people[kind]:
                by_employee_day[(employee_id, key)].add(kind)

    for (employee_id, key), kinds in by_employee_day.items():
        if len(kinds) > 1:
            errors.append(
                f"Xung đột HARD: {employee_names.get(employee_id, employee_id)} ngày {key} có nhiều yêu cầu {', '.join(sorted(kinds))}"
            )

    for key, people in hard_by_day.items():
        target = effective_staffing[key]
        if len(people["MORNING"]) > target["morning"]:
            errors.append(
                f"{key}: số người bắt buộc Sáng ({len(people['MORNING'])}) vượt phân bổ sau OFF {target['morning']}"
            )
        if len(people["AFTERNOON"]) > target["afternoon"]:
            errors.append(
                f"{key}: số người bắt buộc Chiều ({len(people['AFTERNOON'])}) vượt phân bổ sau OFF {target['afternoon']}"
            )
    return errors

def _build_and_solve(config: dict[str, Any], variant: str) -> dict[str, Any] | None:
    weights = VARIANT_WEIGHTS[variant]
    employees = config["active_employees"]
    employee_ids = [item["id"] for item in employees]
    employee_by_id = {item["id"]: item for item in employees}
    days = _week_dates(_parse_date(config["week_start"]))
    day_keys = [item.isoformat() for item in days]
    effective_staffing = _effective_staffing_by_date(config)
    _, hard_off_counts = _hard_day_sets(config)

    model = cp_model.CpModel()
    morning = {(e, d): model.NewBoolVar(f"m_{e}_{d}") for e in employee_ids for d in day_keys}
    afternoon = {(e, d): model.NewBoolVar(f"a_{e}_{d}") for e in employee_ids for d in day_keys}
    receiving = {(e, d): model.NewBoolVar(f"r_{e}_{d}") for e in employee_ids for d in day_keys}
    staffing_terms = []
    manager_target_terms = []
    manager_trend_terms = []
    soft_terms = []

    for e in employee_ids:
        for d in day_keys:
            model.Add(morning[e, d] + afternoon[e, d] <= 1)
            if d not in config["receiving_by_date"]:
                model.Add(receiving[e, d] == 0)
            else:
                model.Add(receiving[e, d] <= afternoon[e, d])

    # Weekday rules first; week-specific hard requests may reinforce them.
    for rule in config["fixed_weekday_rules"]:
        d = day_keys[rule["weekday"]]
        variable = morning[rule["employee_id"], d] if rule["shift"] == "MORNING" else afternoon[rule["employee_id"], d]
        if rule["shift"] == "OFF":
            if rule["level"] == "HARD":
                model.Add(morning[rule["employee_id"], d] == 0)
                model.Add(afternoon[rule["employee_id"], d] == 0)
            else:
                soft_terms.append((morning[rule["employee_id"], d], weights["preference"]))
                soft_terms.append((afternoon[rule["employee_id"], d], weights["preference"]))
        elif rule["level"] == "HARD":
            model.Add(variable == 1)
        else:
            miss = model.NewBoolVar(f"fixed_soft_{rule['employee_id']}_{d}")
            model.Add(miss + variable == 1)
            soft_terms.append((miss, weights["preference"]))

    for request in config["requests"]:
        e, d, kind = request["employee_id"], request["date"], request["type"]
        if kind == "OFF":
            model.Add(morning[e, d] == 0)
            model.Add(afternoon[e, d] == 0)
        elif kind == "MUST_MORNING":
            model.Add(morning[e, d] == 1)
        elif kind == "MUST_AFTERNOON":
            model.Add(afternoon[e, d] == 1)
        else:
            target = morning[e, d] if kind == "PREFER_MORNING" else afternoon[e, d]
            miss = model.NewBoolVar(f"pref_{e}_{d}_{kind}")
            model.Add(miss + target == 1)
            soft_terms.append((miss, weights["preference"]))

    # Generate against the effective staffing target after explicit OFF.
    # This prevents 3S/1C when 2S/2C is the balanced four-person split.
    shortage_vars: dict[tuple[str, str], cp_model.IntVar] = {}
    for d in day_keys:
        target = effective_staffing[d]
        for shift_name, variables, wanted in (
            ("MORNING", morning, target["morning"]),
            ("AFTERNOON", afternoon, target["afternoon"]),
        ):
            total = sum(variables[e, d] for e in employee_ids)
            model.Add(total <= wanted)
            shortage = model.NewIntVar(0, wanted, f"short_{shift_name}_{d}")
            model.Add(total + shortage == wanted)
            shortage_vars[d, shift_name] = shortage
            staffing_terms.append((shortage, 1))

    receiving_shortage: dict[str, cp_model.IntVar] = {}
    for d, nominal_wanted in config["receiving_by_date"].items():
        wanted = min(int(nominal_wanted), int(effective_staffing[d]["afternoon"]))
        total = sum(receiving[e, d] for e in employee_ids)
        model.Add(total <= wanted)
        shortage = model.NewIntVar(0, wanted, f"recv_short_{d}")
        model.Add(total + shortage == wanted)
        receiving_shortage[d] = shortage
        staffing_terms.append((shortage, 1))

    morning_counts = {}
    afternoon_counts = {}
    receiving_counts = {}
    switch_vars: dict[tuple[str, int], cp_model.BoolVar] = {}
    for e in employee_ids:
        morning_count = model.NewIntVar(0, 7, f"mcount_{e}")
        afternoon_count = model.NewIntVar(0, 7, f"acount_{e}")
        receiving_count = model.NewIntVar(0, len(config["receiving_by_date"]), f"rcount_{e}")
        model.Add(morning_count == sum(morning[e, d] for d in day_keys))
        model.Add(afternoon_count == sum(afternoon[e, d] for d in day_keys))
        model.Add(receiving_count == sum(receiving[e, d] for d in day_keys))
        morning_counts[e], afternoon_counts[e], receiving_counts[e] = morning_count, afternoon_count, receiving_count

        rule = config["employee_rules"].get(e, {})
        # An employee with explicit OFF is not compared against a full 7-day S/C target.
        # Full-availability employees keep their targets and therefore get balancing priority.
        if hard_off_counts.get(e, 0) == 0:
            for field, count_var in (("target_morning", morning_count), ("target_afternoon", afternoon_count)):
                target = rule.get(field)
                if target is not None:
                    delta = model.NewIntVar(0, 7, f"delta_{field}_{e}")
                    model.AddAbsEquality(delta, count_var - int(target))
                    if employee_by_id[e]["role"] == "STORE_MANAGER":
                        manager_target_terms.append((delta, 1))
                    else:
                        soft_terms.append((delta, weights["shift_target"]))

        if rule.get("off_receiving_compensation") and hard_off_counts.get(e, 0) > 0:
            soft_terms.append((
                receiving_count,
                -weights["off_receiving_compensation"] * int(hard_off_counts[e]),
            ))

        recv_min = rule.get("receiving_min")
        recv_max = rule.get("receiving_max")
        recv_target = rule.get("receiving_target")
        if recv_max is not None:
            model.Add(receiving_count <= int(recv_max))
        if recv_min is not None:
            miss_min = model.NewIntVar(0, len(config["receiving_by_date"]), f"recv_min_miss_{e}")
            model.Add(receiving_count + miss_min >= int(recv_min))
            soft_terms.append((miss_min, weights["receiving_target"]))
        if recv_target is not None:
            delta = model.NewIntVar(0, len(config["receiving_by_date"]), f"recv_delta_{e}")
            model.AddAbsEquality(delta, receiving_count - int(recv_target))
            soft_terms.append((delta, weights["receiving_target"]))

        for index in range(1, len(day_keys)):
            previous, current = day_keys[index - 1], day_keys[index]
            switch = model.NewBoolVar(f"switch_{e}_{index}")
            model.Add(switch >= morning[e, previous] + afternoon[e, current] - 1)
            model.Add(switch >= afternoon[e, previous] + morning[e, current] - 1)
            switch_vars[e, index] = switch
            soft_terms.append((switch, weights["switch"]))

    # Store-manager trend is optimized lexicographically after staffing and the manager weekly S/C target,
    # then ordinary SOFT goals run last. This enforces priority instead of relying on fragile weight sums.
    if config.get("manager_trend", {}).get("enabled", True):
        trend_by_weekday = {
            int(item["weekday"]): item
            for item in config["manager_trend"]["scores"]
        }
        manager_ids = [
            e for e in employee_ids
            if employee_by_id[e]["role"] == "STORE_MANAGER"
        ]
        for e in manager_ids:
            for day_index, d in enumerate(day_keys):
                score = trend_by_weekday.get(day_index, {"morning": 0, "afternoon": 0})
                morning_score = int(score.get("morning", 0))
                afternoon_score = int(score.get("afternoon", 0))
                best = max(morning_score, afternoon_score)
                if best > morning_score:
                    manager_trend_terms.append((morning[e, d], best - morning_score))
                if best > afternoon_score:
                    manager_trend_terms.append((afternoon[e, d], best - afternoon_score))

    # Fairness spread among non-managers, so the CHT role target is not flattened away.
    staff_ids = [e for e in employee_ids if employee_by_id[e]["role"] != "STORE_MANAGER" and hard_off_counts.get(e, 0) == 0]
    if len(staff_ids) >= 2:
        max_a = model.NewIntVar(0, 7, "max_staff_afternoon")
        min_a = model.NewIntVar(0, 7, "min_staff_afternoon")
        model.AddMaxEquality(max_a, [afternoon_counts[e] for e in staff_ids])
        model.AddMinEquality(min_a, [afternoon_counts[e] for e in staff_ids])
        spread = model.NewIntVar(0, 7, "staff_afternoon_spread")
        model.Add(spread == max_a - min_a)
        soft_terms.append((spread, weights["fairness"]))
        if config["receiving_by_date"]:
            max_r = model.NewIntVar(0, 7, "max_staff_receiving")
            min_r = model.NewIntVar(0, 7, "min_staff_receiving")
            model.AddMaxEquality(max_r, [receiving_counts[e] for e in staff_ids])
            model.AddMinEquality(min_r, [receiving_counts[e] for e in staff_ids])
            recv_spread = model.NewIntVar(0, 7, "staff_receiving_spread")
            model.Add(recv_spread == max_r - min_r)
            soft_terms.append((recv_spread, weights["fairness"]))

    # Pairing rules count being in the same actual shift, not merely working on the same day.
    for p_index, rule in enumerate(config["pairing_rules"]):
        a, b = rule["employee_a"], rule["employee_b"]
        same_vars = []
        receiving_same_vars = []
        for d in day_keys:
            same_m = model.NewBoolVar(f"pair_m_{p_index}_{d}")
            same_a = model.NewBoolVar(f"pair_a_{p_index}_{d}")
            model.Add(same_m <= morning[a, d]); model.Add(same_m <= morning[b, d]); model.Add(same_m >= morning[a, d] + morning[b, d] - 1)
            model.Add(same_a <= afternoon[a, d]); model.Add(same_a <= afternoon[b, d]); model.Add(same_a >= afternoon[a, d] + afternoon[b, d] - 1)
            same_vars.extend([same_m, same_a])
            if d in config["receiving_by_date"]:
                receiving_same_vars.append(same_a)

        total_same = sum(same_vars)
        relation_type = rule["relation_type"]
        count = rule["count"]
        level = rule["level"]

        if relation_type == "MAX":
            if level == "HARD":
                model.Add(total_same <= count)
            else:
                excess = model.NewIntVar(0, 7, f"pair_max_excess_{p_index}")
                model.Add(excess >= total_same - count)
                soft_terms.append((excess, weights["pairing"]))
        elif relation_type == "MIN":
            if level == "HARD":
                model.Add(total_same >= count)
            else:
                shortfall = model.NewIntVar(0, 7, f"pair_min_shortfall_{p_index}")
                model.Add(shortfall >= count - total_same)
                soft_terms.append((shortfall, weights["pairing"]))
        elif relation_type == "EXACT":
            if level == "HARD":
                model.Add(total_same == count)
            else:
                over = model.NewIntVar(0, 7, f"pair_exact_over_{p_index}")
                under = model.NewIntVar(0, 7, f"pair_exact_under_{p_index}")
                model.Add(over >= total_same - count)
                model.Add(under >= count - total_same)
                soft_terms.append((over, weights["pairing"]))
                soft_terms.append((under, weights["pairing"]))
        elif relation_type == "NEVER":
            model.Add(total_same == 0)
        elif relation_type == "PREFER_TOGETHER":
            shortfall = model.NewIntVar(0, 7, f"pair_together_shortfall_{p_index}")
            model.Add(shortfall >= count - total_same)
            soft_terms.append((shortfall, weights["pairing"]))
        elif relation_type == "PREFER_APART":
            soft_terms.append((total_same, weights["pairing"]))

        receiving_relation = rule["receiving_relation"]
        for r_index, same_a in enumerate(receiving_same_vars):
            if receiving_relation == "NEVER":
                model.Add(same_a == 0)
            elif receiving_relation == "AVOID":
                soft_terms.append((same_a, weights["pairing"]))
            elif receiving_relation == "PREFER_TOGETHER":
                miss = model.NewBoolVar(f"pair_receiving_miss_{p_index}_{r_index}")
                model.Add(miss + same_a == 1)
                soft_terms.append((miss, weights["pairing"]))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 4.0
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0

    objective_levels = [
        ("staffing", staffing_terms),
        ("manager_target", manager_target_terms),
        ("manager_trend", manager_trend_terms),
        ("soft", soft_terms),
    ]
    objective_breakdown: dict[str, int] = {}
    status = cp_model.UNKNOWN
    for level_name, terms in objective_levels:
        if not terms:
            objective_breakdown[level_name] = 0
            continue
        expr = sum(var * weight for var, weight in terms)
        model.Minimize(expr)
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None
        optimum = int(round(solver.ObjectiveValue()))
        objective_breakdown[level_name] = optimum
        model.Add(expr == optimum)

    if status == cp_model.UNKNOWN:
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

    assignments = []
    for employee in employees:
        e = employee["id"]
        for d in day_keys:
            if solver.Value(morning[e, d]):
                shift = "MORNING"
            elif solver.Value(afternoon[e, d]):
                shift = "AFTERNOON"
            else:
                shift = "OFF"
            assignments.append({
                "employee_id": e,
                "date": d,
                "shift": shift,
                "receiving": bool(solver.Value(receiving[e, d])) if shift == "AFTERNOON" else False,
                "start_time": None,
            })

    assignments = assign_morning_times(config, assignments)
    validation = validate_schedule(config, assignments)
    return {
        "variant": variant,
        "label": VARIANT_LABELS[variant],
        "objective": objective_breakdown,
        "assignments": assignments,
        "metrics": validation["metrics"],
        "warnings": validation["warnings"],
        "status": validation["status"],
    }


def assign_morning_times(config: dict[str, Any], assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = deepcopy(assignments)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    employees = {item["id"]: item for item in config["active_employees"]}
    override_map = {(item["employee_id"], item["date"]): item["start"] for item in config["morning_time_overrides"]}
    late_count = defaultdict(int)
    for row in result:
        if row["shift"] == "MORNING":
            by_day[row["date"]].append(row)
        else:
            row["start_time"] = "14:00" if row["shift"] == "AFTERNOON" else None

    employee_order = {item["id"]: index for index, item in enumerate(config["active_employees"])}
    for day in sorted(by_day):
        rows = by_day[day]
        if len(rows) > 3:
            raise SchedulingError(f"{day}: template chỉ hỗ trợ tối đa 3 người ca sáng")
        if len(rows) <= 2:
            for row in rows:
                forced = override_map.get((row["employee_id"], day))
                if forced == "07:00":
                    raise SchedulingError(f"{day}: chỉ có {len(rows)} người sáng nên không được xếp 07:00")
                row["start_time"] = "06:00"
            continue

        forced_07 = [row for row in rows if override_map.get((row["employee_id"], day)) == "07:00"]
        if len(forced_07) > 1:
            raise SchedulingError(f"{day}: chỉ có 1 vị trí 07:00–15:00")
        blocked_06 = {row["employee_id"] for row in rows if override_map.get((row["employee_id"], day)) == "06:00"}
        if forced_07:
            late = forced_07[0]
        else:
            candidates = [row for row in rows if row["employee_id"] not in blocked_06]
            if not candidates:
                raise SchedulingError(f"{day}: cả 3 người sáng đều bị khóa 06:00, không còn người cho ca 07:00")
            managers = [row for row in candidates if employees[row["employee_id"]]["role"] == "STORE_MANAGER"]
            pool = managers or candidates
            late = min(pool, key=lambda row: (late_count[row["employee_id"]], employee_order[row["employee_id"]]))
        for row in rows:
            row["start_time"] = "07:00" if row is late else "06:00"
        late_count[late["employee_id"]] += 1
    return result


def calculate_metrics(config: dict[str, Any], assignments: list[dict[str, Any]]) -> dict[str, Any]:
    active = config["active_employees"]
    _, hard_off_counts = _hard_day_sets(config)
    by_employee: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in assignments:
        by_employee[row["employee_id"]].append(row)
    employee_metrics = []
    total_switches = 0
    total_soft_misses = 0
    for employee in active:
        rows = sorted(by_employee.get(employee["id"], []), key=lambda item: item["date"])
        morning = sum(row["shift"] == "MORNING" for row in rows)
        afternoon = sum(row["shift"] == "AFTERNOON" for row in rows)
        receiving = sum(bool(row.get("receiving")) for row in rows)
        late = sum(row["shift"] == "MORNING" and row.get("start_time") == "07:00" for row in rows)
        switches = 0
        previous = None
        for row in rows:
            current = row["shift"]
            if current == "OFF":
                previous = None
                continue
            if previous and previous != current:
                switches += 1
            previous = current
        total_switches += switches
        employee_metrics.append({
            "employee_id": employee["id"],
            "name": employee["name"],
            "morning": morning,
            "afternoon": afternoon,
            "off": sum(row["shift"] == "OFF" for row in rows),
            "receiving": receiving,
            "switches": switches,
            "morning_0700": late,
            "requested_off": hard_off_counts.get(employee["id"], 0),
            "off_receiving_compensation": bool(
                config["employee_rules"].get(employee["id"], {}).get("off_receiving_compensation", False)
            ),
        })

    lookup = {(row["employee_id"], row["date"]): row for row in assignments}
    for request in config["requests"]:
        row = lookup.get((request["employee_id"], request["date"]))
        if not row:
            continue
        if request["type"] == "PREFER_MORNING" and row["shift"] != "MORNING":
            total_soft_misses += 1
        if request["type"] == "PREFER_AFTERNOON" and row["shift"] != "AFTERNOON":
            total_soft_misses += 1

    afternoons = [
        item["afternoon"] for item in employee_metrics
        if next(e for e in active if e["id"] == item["employee_id"])["role"] != "STORE_MANAGER"
        and hard_off_counts.get(item["employee_id"], 0) == 0
    ]
    receivings = [
        item["receiving"] for item in employee_metrics
        if next(e for e in active if e["id"] == item["employee_id"])["role"] != "STORE_MANAGER"
        and hard_off_counts.get(item["employee_id"], 0) == 0
    ]
    return {
        "employees": employee_metrics,
        "total_switches": total_switches,
        "soft_requests_missed": total_soft_misses,
        "afternoon_spread": (max(afternoons) - min(afternoons)) if afternoons else 0,
        "receiving_spread": (max(receivings) - min(receivings)) if receivings else 0,
    }


def validate_schedule(config_or_payload: dict[str, Any], assignments: list[dict[str, Any]]) -> dict[str, Any]:
    config = config_or_payload if "staffing_by_date" in config_or_payload else normalize_config(config_or_payload)
    active_ids = {item["id"] for item in config["active_employees"]}
    employee_by_id = {item["id"]: item for item in config["active_employees"]}
    day_keys = [item.isoformat() for item in _week_dates(_parse_date(config["week_start"]))]
    effective_staffing = _effective_staffing_by_date(config)
    _, hard_off_counts = _hard_day_sets(config)
    expected = {(e, d) for e in active_ids for d in day_keys}
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    errors: list[str] = []
    warnings: list[str] = []
    for position, raw in enumerate(assignments or []):
        if not isinstance(raw, dict):
            errors.append(f"assignments[{position}] không hợp lệ")
            continue
        e = str(raw.get("employee_id") or "")
        d = str(raw.get("date") or "")
        shift = str(raw.get("shift") or "").upper()
        if e not in active_ids or d not in day_keys or shift not in SHIFTS:
            errors.append(f"Dòng lịch không hợp lệ: {e} {d} {shift}")
            continue
        key = (e, d)
        if key in lookup:
            errors.append(f"{e} ngày {d} xuất hiện nhiều hơn một lần")
            continue
        start_time = raw.get("start_time")
        if shift == "MORNING" and start_time not in {"06:00", "07:00"}:
            errors.append(f"{employee_by_id[e]['name']} ngày {d}: ca Sáng phải có giờ 06:00 hoặc 07:00")
        if shift == "AFTERNOON" and start_time not in {None, "14:00"}:
            errors.append(f"{employee_by_id[e]['name']} ngày {d}: ca Chiều bắt đầu 14:00")
        lookup[key] = {
            "employee_id": e, "date": d, "shift": shift,
            "start_time": start_time if shift == "MORNING" else ("14:00" if shift == "AFTERNOON" else None),
            "receiving": bool(raw.get("receiving")) if shift == "AFTERNOON" else False,
        }
    missing = expected - set(lookup)
    if missing:
        errors.append(f"Thiếu {len(missing)} ô lịch nhân viên/ngày")

    start = _parse_date(config["week_start"])
    hard_rules = []
    for rule in config["fixed_weekday_rules"]:
        if rule["level"] == "HARD":
            hard_rules.append({"employee_id": rule["employee_id"], "date": (start + timedelta(days=rule["weekday"])).isoformat(), "type": {"MORNING": "MUST_MORNING", "AFTERNOON": "MUST_AFTERNOON", "OFF": "OFF"}[rule["shift"]]})
    hard_rules.extend([item for item in config["requests"] if item["type"] in {"OFF", "MUST_MORNING", "MUST_AFTERNOON"}])
    for rule in hard_rules:
        row = lookup.get((rule["employee_id"], rule["date"]))
        if not row:
            continue
        expected_shift = {"OFF": "OFF", "MUST_MORNING": "MORNING", "MUST_AFTERNOON": "AFTERNOON"}[rule["type"]]
        if row["shift"] != expected_shift:
            errors.append(f"Vi phạm HARD: {employee_by_id[rule['employee_id']]['name']} {rule['date']} phải {expected_shift}")

    for rule in config["fixed_weekday_rules"]:
        if rule["level"] != "SOFT":
            continue
        d = (start + timedelta(days=rule["weekday"])).isoformat()
        row = lookup.get((rule["employee_id"], d))
        if row and row["shift"] != rule["shift"]:
            warnings.append(
                f"Ưu tiên chưa đạt: {employee_by_id[rule['employee_id']]['name']} {d} mong muốn {rule['shift']}"
            )
    for request in config["requests"]:
        if request["type"] not in {"PREFER_MORNING", "PREFER_AFTERNOON"}:
            continue
        row = lookup.get((request["employee_id"], request["date"]))
        wanted = "MORNING" if request["type"] == "PREFER_MORNING" else "AFTERNOON"
        if row and row["shift"] != wanted:
            warnings.append(
                f"Nguyện vọng chưa đạt: {employee_by_id[request['employee_id']]['name']} {request['date']} ưu tiên {wanted}"
            )

    for d in day_keys:
        rows = [row for row in lookup.values() if row["date"] == d]
        morning_rows = [row for row in rows if row["shift"] == "MORNING"]
        afternoon_rows = [row for row in rows if row["shift"] == "AFTERNOON"]
        nominal = config["staffing_by_date"][d]
        target = effective_staffing[d]
        if len(morning_rows) > nominal["morning"]:
            errors.append(f"{d}: ca Sáng có {len(morning_rows)} người, vượt giới hạn {nominal['morning']}")
        elif len(morning_rows) < target["morning"]:
            warnings.append(f"{d}: ca Sáng thiếu {target['morning'] - len(morning_rows)} người so với phân bổ sau OFF")
        elif len(morning_rows) > target["morning"]:
            warnings.append(f"{d}: ca Sáng cao hơn phân bổ cân bằng sau OFF ({len(morning_rows)}/{target['morning']})")
        if len(afternoon_rows) > nominal["afternoon"]:
            errors.append(f"{d}: ca Chiều có {len(afternoon_rows)} người, vượt giới hạn {nominal['afternoon']}")
        elif len(afternoon_rows) < target["afternoon"]:
            warnings.append(f"{d}: ca Chiều thiếu {target['afternoon'] - len(afternoon_rows)} người so với phân bổ sau OFF")
        elif len(afternoon_rows) > target["afternoon"]:
            warnings.append(f"{d}: ca Chiều cao hơn phân bổ cân bằng sau OFF ({len(afternoon_rows)}/{target['afternoon']})")

        if len(morning_rows) <= 2:
            for row in morning_rows:
                if row["start_time"] != "06:00":
                    errors.append(f"{d}: khi chỉ có {len(morning_rows)} người sáng, tất cả phải vào 06:00")
        elif len(morning_rows) == 3:
            late = [row for row in morning_rows if row["start_time"] == "07:00"]
            if len(late) != 1:
                errors.append(f"{d}: 3 người sáng phải có đúng 1 người làm 07:00–15:00")
            else:
                managers = [row for row in morning_rows if employee_by_id[row["employee_id"]]["role"] == "STORE_MANAGER"]
                hard_06 = {(item["employee_id"], item["date"]) for item in config["morning_time_overrides"] if item["start"] == "06:00"}
                if len(managers) == 1 and (managers[0]["employee_id"], d) not in hard_06 and late[0]["employee_id"] != managers[0]["employee_id"]:
                    warnings.append(f"{d}: mặc định CHT nên làm 07:00–15:00 khi có 3 người sáng")

        for override in config["morning_time_overrides"]:
            if override["date"] != d:
                continue
            row = lookup.get((override["employee_id"], d))
            if not row:
                continue
            if row["shift"] != "MORNING":
                errors.append(
                    f"Vi phạm HARD giờ ca: {employee_by_id[override['employee_id']]['name']} {d} phải làm ca Sáng {override['start']}"
                )
            elif row["start_time"] != override["start"]:
                errors.append(
                    f"Vi phạm HARD giờ ca: {employee_by_id[override['employee_id']]['name']} {d} phải vào {override['start']}"
                )

        receiving_rows = [row for row in afternoon_rows if row["receiving"]]
        if d not in config["receiving_by_date"] and receiving_rows:
            errors.append(f"{d}: không phải ngày nhận hàng nhưng có người được đánh dấu nhận hàng")
        if d in config["receiving_by_date"]:
            wanted = min(int(config["receiving_by_date"][d]), int(target["afternoon"]))
            if len(receiving_rows) < wanted:
                warnings.append(f"{d}: nhận hàng thiếu {wanted - len(receiving_rows)} người so với target sau OFF {wanted}")
            if len(receiving_rows) > wanted:
                warnings.append(f"{d}: nhận hàng vượt target sau OFF {wanted}")

    for rule in config["pairing_rules"]:
        a, b = rule["employee_a"], rule["employee_b"]
        same = 0
        receiving_same = 0
        receiving_days = len(config["receiving_by_date"])
        for d in day_keys:
            left, right = lookup.get((a, d)), lookup.get((b, d))
            if left and right and left["shift"] in {"MORNING", "AFTERNOON"} and left["shift"] == right["shift"]:
                same += 1
                if d in config["receiving_by_date"] and left["shift"] == "AFTERNOON":
                    receiving_same += 1

        left_name = employee_by_id[a]["name"]
        right_name = employee_by_id[b]["name"]
        relation_type = rule["relation_type"]
        count = rule["count"]
        level = rule["level"]
        severity = errors if level == "HARD" else warnings

        if relation_type == "MAX" and same > count:
            severity.append(f"{left_name} và {right_name} chung {same} ca, vượt tối đa {count}")
        elif relation_type == "MIN" and same < count:
            severity.append(f"{left_name} và {right_name} chỉ chung {same} ca, dưới tối thiểu {count}")
        elif relation_type == "EXACT" and same != count:
            severity.append(f"{left_name} và {right_name} chung {same} ca, cần chính xác {count}")
        elif relation_type == "NEVER" and same:
            errors.append(f"{left_name} và {right_name} không được chung ca nhưng đang chung {same} ca")
        elif relation_type == "PREFER_TOGETHER" and same < count:
            warnings.append(f"{left_name} và {right_name} chỉ chung {same}/{count} ca theo ưu tiên")
        elif relation_type == "PREFER_APART" and same:
            warnings.append(f"{left_name} và {right_name} vẫn chung {same} ca dù ưu tiên tránh chung")

        receiving_relation = rule["receiving_relation"]
        if receiving_relation == "NEVER" and receiving_same:
            errors.append(f"{left_name} và {right_name} không được chung ca Chiều ngày nhận hàng nhưng đang chung {receiving_same} ngày")
        elif receiving_relation == "AVOID" and receiving_same:
            warnings.append(f"{left_name} và {right_name} chung ca Chiều {receiving_same} ngày nhận hàng dù ưu tiên tránh")
        elif receiving_relation == "PREFER_TOGETHER" and receiving_days and receiving_same < receiving_days:
            warnings.append(f"{left_name} và {right_name} chung ca Chiều {receiving_same}/{receiving_days} ngày nhận hàng theo ưu tiên")

    metrics = calculate_metrics(config, list(lookup.values())) if not missing else {"employees": [], "total_switches": 0, "soft_requests_missed": 0, "afternoon_spread": 0, "receiving_spread": 0}
    metric_by_employee = {item["employee_id"]: item for item in metrics.get("employees", [])}
    for employee_id, rule in config["employee_rules"].items():
        metric = metric_by_employee.get(employee_id)
        if not metric:
            continue
        receiving_max = rule.get("receiving_max")
        if receiving_max is not None and metric["receiving"] > int(receiving_max):
            errors.append(
                f"{employee_by_id[employee_id]['name']}: nhận hàng {metric['receiving']} vượt tối đa {receiving_max}"
            )
        receiving_min = rule.get("receiving_min")
        if receiving_min is not None and metric["receiving"] < int(receiving_min):
            warnings.append(
                f"{employee_by_id[employee_id]['name']}: nhận hàng {metric['receiving']} dưới mục tiêu tối thiểu {receiving_min}"
            )
        if hard_off_counts.get(employee_id, 0) == 0:
            for field, metric_field, label in (
                ("target_morning", "morning", "ca Sáng"),
                ("target_afternoon", "afternoon", "ca Chiều"),
            ):
                target = rule.get(field)
                if target is not None and metric[metric_field] != int(target):
                    warnings.append(
                        f"{employee_by_id[employee_id]['name']}: {label} {metric[metric_field]}/{target} so với target"
                    )

        receiving_target = rule.get("receiving_target")
        if receiving_target is not None:
            compensation = bool(rule.get("off_receiving_compensation")) and hard_off_counts.get(employee_id, 0) > 0
            misses_target = metric["receiving"] < int(receiving_target) if compensation else metric["receiving"] != int(receiving_target)
            if misses_target:
                warnings.append(
                    f"{employee_by_id[employee_id]['name']}: buổi nhận hàng {metric['receiving']}/{receiving_target} so với target"
                )
    status = "INVALID" if errors else ("VALID_WITH_WARNINGS" if warnings else "VALID")
    return {"status": status, "errors": errors, "warnings": warnings, "metrics": metrics, "assignments": list(lookup.values())}


def generate_schedule(payload: dict[str, Any], *, variants: int = 3) -> dict[str, Any]:
    config = normalize_config(payload)
    precheck = _hard_precheck(config)
    if precheck:
        return {"status": "INVALID", "errors": precheck, "warnings": [], "config": public_config(config), "options": []}
    wanted_variants = max(1, min(int(variants or 3), 3))
    options = []
    signatures = set()
    for variant in ("balanced", "stable", "preferences")[:wanted_variants]:
        solved = _build_and_solve(config, variant)
        if solved is None:
            continue
        signature = tuple((row["employee_id"], row["date"], row["shift"], row.get("start_time"), bool(row.get("receiving"))) for row in solved["assignments"])
        if signature in signatures:
            continue
        signatures.add(signature)
        options.append(solved)
    if not options:
        return {
            "status": "INVALID",
            "errors": ["Không tìm được lịch thỏa các HARD constraint. Hãy kiểm tra OFF, ca bắt buộc, giới hạn nhân sự và quan hệ HARD."],
            "warnings": [],
            "config": public_config(config),
            "options": [],
        }
    status = "VALID_WITH_WARNINGS" if any(option["warnings"] for option in options) else "VALID"
    return {"status": status, "errors": [], "warnings": [], "config": public_config(config), "options": options}


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe config that can be fed back into ``normalize_config``.

    Internal lookup dictionaries must not leak as the public API shape; otherwise
    generated schedules would lose receiving days/employee quotas when the user
    validates or saves them again.
    """
    result = {
        key: deepcopy(value)
        for key, value in config.items()
        if key not in {"active_employees", "staffing_by_date", "receiving_by_date", "employee_rules"}
    }
    result["receiving_days"] = [
        {"date": key, "count": int(value)}
        for key, value in sorted(config.get("receiving_by_date", {}).items())
    ]
    result["employee_rules"] = [
        {"employee_id": employee_id, **deepcopy(rule)}
        for employee_id, rule in config.get("employee_rules", {}).items()
    ]
    return result