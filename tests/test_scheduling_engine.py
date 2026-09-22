import pytest
from copy import deepcopy

from modules.scheduling_engine import generate_schedule, normalize_config, public_config, validate_schedule


def config():
    employees = [
        {"id": "phuong", "name": "Phương", "staff_code": "800603", "role": "STORE_MANAGER", "active": True},
        {"id": "mi", "name": "Mi", "staff_code": "825982", "role": "EMPLOYEE", "active": True},
        {"id": "nhan", "name": "Nhàn", "staff_code": "827370", "role": "EMPLOYEE", "active": True},
        {"id": "vu", "name": "Vũ", "staff_code": "825433", "role": "EMPLOYEE", "active": True},
        {"id": "ly", "name": "Ly", "staff_code": "827389", "role": "EMPLOYEE", "active": True},
    ]
    days = [f"2026-09-{day:02d}" for day in range(14, 21)]
    return {
        "store_label": "1885",
        "week_start": days[0],
        "employees": employees,
        "staffing": [
            {"date": day, "morning": 3 if index == 0 else 2, "afternoon": 2 if index == 0 else 3}
            for index, day in enumerate(days)
        ],
        "receiving_days": [
            {"date": "2026-09-15", "count": 3},
            {"date": "2026-09-17", "count": 3},
            {"date": "2026-09-19", "count": 3},
        ],
        "requests": [],
        "fixed_weekday_rules": [
            {"employee_id": "phuong", "weekday": 0, "shift": "MORNING", "level": "HARD"},
            {"employee_id": "phuong", "weekday": 1, "shift": "AFTERNOON", "level": "HARD"},
        ],
        "employee_rules": [
            {"employee_id": "phuong", "target_morning": 3, "target_afternoon": 4, "receiving_target": 1, "receiving_max": 1},
            {"employee_id": "mi", "target_morning": 3, "target_afternoon": 4, "receiving_target": 1, "receiving_max": 2},
            {"employee_id": "nhan", "target_morning": 3, "target_afternoon": 4, "receiving_target": 3, "receiving_max": 3},
            {"employee_id": "vu", "target_morning": 3, "target_afternoon": 4, "receiving_target": 2, "receiving_max": 3},
            {"employee_id": "ly", "target_morning": 3, "target_afternoon": 4, "receiving_target": 2, "receiving_max": 3},
        ],
        "pairing_rules": [],
        "morning_time_overrides": [],
    }


def lookup(assignments):
    return {(row["employee_id"], row["date"]): row for row in assignments}


def test_generate_respects_hard_requests_and_manager_morning_hour_rule():
    payload = config()
    payload["requests"] = [
        {"employee_id": "vu", "date": "2026-09-16", "type": "MUST_MORNING"},
        {"employee_id": "mi", "date": "2026-09-18", "type": "OFF"},
        {"employee_id": "ly", "date": "2026-09-20", "type": "MUST_AFTERNOON"},
    ]

    result = generate_schedule(payload)

    assert result["options"]
    rows = lookup(result["options"][0]["assignments"])
    assert rows[("vu", "2026-09-16")]["shift"] == "MORNING"
    assert rows[("mi", "2026-09-18")]["shift"] == "OFF"
    assert rows[("ly", "2026-09-20")]["shift"] == "AFTERNOON"
    assert rows[("phuong", "2026-09-14")]["shift"] == "MORNING"
    assert rows[("phuong", "2026-09-14")]["start_time"] == "07:00"
    monday_morning = [row for row in rows.values() if row["date"] == "2026-09-14" and row["shift"] == "MORNING"]
    assert sorted(row["start_time"] for row in monday_morning) == ["06:00", "06:00", "07:00"]
    tuesday_morning = [row for row in rows.values() if row["date"] == "2026-09-15" and row["shift"] == "MORNING"]
    assert len(tuesday_morning) == 2
    assert {row["start_time"] for row in tuesday_morning} == {"06:00"}


def test_manager_can_be_hard_locked_to_0600_and_another_morning_gets_0700():
    payload = config()
    payload["morning_time_overrides"] = [
        {"employee_id": "phuong", "date": "2026-09-14", "start": "06:00"},
    ]

    result = generate_schedule(payload)

    rows = lookup(result["options"][0]["assignments"])
    monday_morning = [row for row in rows.values() if row["date"] == "2026-09-14" and row["shift"] == "MORNING"]
    assert rows[("phuong", "2026-09-14")]["start_time"] == "06:00"
    assert sum(row["start_time"] == "07:00" for row in monday_morning) == 1
    assert next(row for row in monday_morning if row["start_time"] == "07:00")["employee_id"] != "phuong"


def test_conflicting_hard_request_is_reported_instead_of_silently_broken():
    payload = config()
    payload["requests"] = [
        {"employee_id": "phuong", "date": "2026-09-14", "type": "OFF"},
    ]

    result = generate_schedule(payload)

    assert result["status"] == "INVALID"
    assert not result["options"]
    assert any("Xung đột HARD" in error for error in result["errors"])


def test_public_config_round_trip_keeps_receiving_days_and_employee_rules():
    normalized = normalize_config(config())
    public = public_config(normalized)
    again = normalize_config(public)

    assert again["receiving_by_date"] == normalized["receiving_by_date"]
    assert again["employee_rules"] == normalized["employee_rules"]
    assert "staffing_by_date" not in public
    assert "active_employees" not in public


def test_manual_edit_cannot_break_off_or_hard_morning_hour_lock():
    payload = config()
    payload["requests"] = [{"employee_id": "mi", "date": "2026-09-18", "type": "OFF"}]
    payload["morning_time_overrides"] = [{"employee_id": "phuong", "date": "2026-09-14", "start": "06:00"}]
    generated = generate_schedule(payload)["options"][0]["assignments"]
    edited = deepcopy(generated)
    for row in edited:
        if row["employee_id"] == "mi" and row["date"] == "2026-09-18":
            row.update(shift="AFTERNOON", start_time="14:00")
        if row["employee_id"] == "phuong" and row["date"] == "2026-09-14":
            row["start_time"] = "07:00"

    validation = validate_schedule(payload, edited)

    assert validation["status"] == "INVALID"
    assert any("Vi phạm HARD" in error for error in validation["errors"])
    assert any("Vi phạm HARD giờ ca" in error for error in validation["errors"])


def test_off_rebalances_daily_staffing_instead_of_creating_three_to_one_split():
    for off_date, expected_morning, expected_afternoon in (
        ("2026-09-14", 2, 2),  # nominal Monday 3S/2C
        ("2026-09-16", 2, 2),  # nominal weekday 2S/3C
    ):
        payload = config()
        payload["requests"] = [{"employee_id": "mi", "date": off_date, "type": "OFF"}]

        option = generate_schedule(payload)["options"][0]
        rows = lookup(option["assignments"])
        morning = [row for row in rows.values() if row["date"] == off_date and row["shift"] == "MORNING"]
        afternoon = [row for row in rows.values() if row["date"] == off_date and row["shift"] == "AFTERNOON"]

        assert rows[("mi", off_date)]["shift"] == "OFF"
        assert len(morning) == expected_morning
        assert len(afternoon) == expected_afternoon
        assert not any(off_date in warning and "thiếu" in warning.lower() for warning in option["warnings"])


def test_manual_three_to_one_after_off_is_warning_not_invalid():
    payload = config()
    payload["requests"] = [{"employee_id": "mi", "date": "2026-09-14", "type": "OFF"}]
    assignments = deepcopy(generate_schedule(payload)["options"][0]["assignments"])
    monday = [row for row in assignments if row["date"] == "2026-09-14"]
    afternoon = next(row for row in monday if row["shift"] == "AFTERNOON")
    afternoon.update(shift="MORNING", start_time="06:00", receiving=False)
    for row in monday:
        if row["employee_id"] == "phuong":
            row["start_time"] = "07:00"

    validation = validate_schedule(payload, assignments)

    assert validation["status"] == "VALID_WITH_WARNINGS"
    assert not validation["errors"]
    assert any("phân bổ cân bằng sau OFF" in warning for warning in validation["warnings"])


def test_employee_with_explicit_off_is_not_warned_against_full_week_shift_targets():
    payload = config()
    payload["requests"] = [{"employee_id": "mi", "date": "2026-09-16", "type": "OFF"}]

    option = generate_schedule(payload)["options"][0]

    assert not any(warning.startswith("Mi: ca Sáng") for warning in option["warnings"])
    assert not any(warning.startswith("Mi: ca Chiều") for warning in option["warnings"])


def test_off_receiving_compensation_prefers_employee_with_more_off_days():
    payload = config()
    payload["receiving_days"] = [{"date": "2026-09-15", "count": 1}]
    payload["employee_rules"] = [
        {
            "employee_id": employee["id"],
            "target_morning": None,
            "target_afternoon": None,
            "receiving_min": 0,
            "receiving_target": None,
            "receiving_max": 3,
            "off_receiving_compensation": employee["id"] in {"mi", "ly"},
        }
        for employee in payload["employees"]
    ]
    payload["requests"] = [
        {"employee_id": "mi", "date": "2026-09-15", "type": "MUST_AFTERNOON"},
        {"employee_id": "ly", "date": "2026-09-15", "type": "MUST_AFTERNOON"},
        {"employee_id": "mi", "date": "2026-09-16", "type": "OFF"},
        {"employee_id": "ly", "date": "2026-09-16", "type": "OFF"},
        {"employee_id": "ly", "date": "2026-09-18", "type": "OFF"},
    ]

    option = generate_schedule(payload)["options"][0]
    rows = lookup(option["assignments"])

    assert rows[("ly", "2026-09-15")]["receiving"] is True
    assert rows[("mi", "2026-09-15")]["receiving"] is False


def test_off_receiving_compensation_flag_round_trips_public_config():
    payload = config()
    for rule in payload["employee_rules"]:
        if rule["employee_id"] == "nhan":
            rule["off_receiving_compensation"] = True

    normalized = normalize_config(payload)
    public = public_config(normalized)
    again = normalize_config(public)

    assert normalized["employee_rules"]["nhan"]["off_receiving_compensation"] is True
    assert again["employee_rules"]["nhan"]["off_receiving_compensation"] is True


def test_receiving_assignment_only_exists_on_receiving_afternoon():
    option = generate_schedule(config())["options"][0]
    receiving_days = {"2026-09-15", "2026-09-17", "2026-09-19"}

    for row in option["assignments"]:
        if row["receiving"]:
            assert row["shift"] == "AFTERNOON"
            assert row["date"] in receiving_days


def test_soft_pairing_receiving_day_rule_warns_but_does_not_become_hard():
    payload = config()
    payload["pairing_rules"] = [{
        "employee_a": "phuong",
        "employee_b": "nhan",
        "max_same_shifts_per_week": None,
        "receiving_day_allowed": False,
        "level": "SOFT",
    }]

    result = generate_schedule(payload)

    assert result["options"]
    # The important contract is that SOFT relationship remains solvable; validator
    # can warn if the optimizer still needs the pair together on receiving day.
    assert result["options"][0]["status"] in {"VALID", "VALID_WITH_WARNINGS"}

def _same_shift_count(assignments, employee_a, employee_b):
    rows = lookup(assignments)
    dates = sorted({date for _, date in rows})
    return sum(
        rows[(employee_a, day)]["shift"] in {"MORNING", "AFTERNOON"}
        and rows[(employee_a, day)]["shift"] == rows[(employee_b, day)]["shift"]
        for day in dates
    )


def test_pairing_legacy_shape_round_trips_to_explicit_relation_contract():
    payload = config()
    payload["pairing_rules"] = [{
        "employee_a": "phuong",
        "employee_b": "nhan",
        "max_same_shifts_per_week": 1,
        "receiving_day_allowed": False,
        "level": "SOFT",
    }]

    normalized = normalize_config(payload)
    rule = normalized["pairing_rules"][0]

    assert rule == {
        "employee_a": "phuong",
        "employee_b": "nhan",
        "relation_type": "MAX",
        "count": 1,
        "level": "SOFT",
        "receiving_relation": "AVOID",
    }


def test_hard_never_pairing_is_not_broken_by_solver():
    payload = config()
    payload["pairing_rules"] = [{
        "employee_a": "phuong",
        "employee_b": "nhan",
        "relation_type": "NEVER",
        "count": 0,
        "level": "HARD",
        "receiving_relation": "NORMAL",
    }]

    result = generate_schedule(payload)

    assert result["options"]
    for option in result["options"]:
        assert _same_shift_count(option["assignments"], "phuong", "nhan") == 0


def test_hard_min_and_exact_pairing_counts_are_enforced():
    for relation_type, count in (("MIN", 2), ("EXACT", 2)):
        payload = config()
        payload["employee_rules"] = []
        payload["pairing_rules"] = [{
            "employee_a": "mi",
            "employee_b": "nhan",
            "relation_type": relation_type,
            "count": count,
            "level": "HARD",
            "receiving_relation": "NORMAL",
        }]

        result = generate_schedule(payload)
        assert result["options"], relation_type
        actual = _same_shift_count(result["options"][0]["assignments"], "mi", "nhan")
        if relation_type == "MIN":
            assert actual >= count
        else:
            assert actual == count


def test_receiving_relation_never_blocks_same_afternoon_on_receiving_days():
    payload = config()
    payload["employee_rules"] = []
    payload["pairing_rules"] = [{
        "employee_a": "phuong",
        "employee_b": "nhan",
        "relation_type": "UNLIMITED",
        "count": None,
        "level": "SOFT",
        "receiving_relation": "NEVER",
    }]

    option = generate_schedule(payload)["options"][0]
    rows = lookup(option["assignments"])
    for day in {"2026-09-15", "2026-09-17", "2026-09-19"}:
        assert not (
            rows[("phuong", day)]["shift"] == "AFTERNOON"
            and rows[("nhan", day)]["shift"] == "AFTERNOON"
        )


def test_soft_prefer_apart_remains_a_warning_not_invalid_after_manual_edit():
    payload = config()
    payload["pairing_rules"] = [{
        "employee_a": "phuong",
        "employee_b": "nhan",
        "relation_type": "PREFER_APART",
        "count": None,
        "level": "SOFT",
        "receiving_relation": "NORMAL",
    }]
    assignments = generate_schedule(config())["options"][0]["assignments"]

    validation = validate_schedule(payload, assignments)

    assert validation["status"] in {"VALID", "VALID_WITH_WARNINGS"}
    assert not validation["errors"]

def _manager_trend_payload(enabled=True):
    # Deliberately extreme scores: solver caps each daily trend gap so weekly
    # target counts remain stronger than trend magnitude.
    return {
        "enabled": enabled,
        "scores": [
            {"weekday": 0, "morning": 0, "afternoon": 10000},  # T2: HARD morning must still win
            {"weekday": 1, "morning": 10000, "afternoon": 0},  # T3: HARD afternoon must still win
            {"weekday": 2, "morning": 10000, "afternoon": 0},
            {"weekday": 3, "morning": 10000, "afternoon": 0},
            {"weekday": 4, "morning": 0, "afternoon": 10000},
            {"weekday": 5, "morning": 0, "afternoon": 10000},
            {"weekday": 6, "morning": 0, "afternoon": 10000},
        ],
    }


def test_manager_trend_chooses_free_days_without_breaking_regional_hard_rules_or_weekly_target():
    payload = config()
    payload["manager_trend"] = _manager_trend_payload()
    # Isolate trend choice from receiving constraints; receiving has its own
    # regression below and must outrank trend when configured.
    payload["receiving_days"] = []
    payload["employee_rules"] = [{
        "employee_id": "phuong",
        "target_morning": 3,
        "target_afternoon": 4,
        "receiving_min": 0,
        "receiving_target": None,
        "receiving_max": None,
    }]

    option = generate_schedule(payload)["options"][0]
    rows = lookup(option["assignments"])

    assert rows[("phuong", "2026-09-14")]["shift"] == "MORNING"    # regional HARD T2
    assert rows[("phuong", "2026-09-15")]["shift"] == "AFTERNOON"  # regional HARD T3
    assert rows[("phuong", "2026-09-16")]["shift"] == "MORNING"
    assert rows[("phuong", "2026-09-17")]["shift"] == "MORNING"
    assert rows[("phuong", "2026-09-18")]["shift"] == "AFTERNOON"
    assert rows[("phuong", "2026-09-19")]["shift"] == "AFTERNOON"
    assert rows[("phuong", "2026-09-20")]["shift"] == "AFTERNOON"

    manager = next(item for item in option["metrics"]["employees"] if item["employee_id"] == "phuong")
    assert manager["morning"] == 3
    assert manager["afternoon"] == 4


def test_user_hard_request_beats_manager_trend():
    payload = config()
    payload["manager_trend"] = _manager_trend_payload()
    payload["requests"] = [
        {"employee_id": "phuong", "date": "2026-09-18", "type": "MUST_MORNING"},
    ]

    result = generate_schedule(payload)

    assert result["options"]
    rows = lookup(result["options"][0]["assignments"])
    assert rows[("phuong", "2026-09-18")]["shift"] == "MORNING"


def test_manager_trend_round_trips_public_config():
    payload = config()
    payload["manager_trend"] = {
        "enabled": True,
        "scores": [
            {"weekday": i, "morning": 10 + i, "afternoon": 20 + i}
            for i in range(7)
        ],
    }

    normalized = normalize_config(payload)
    public = public_config(normalized)
    again = normalize_config(public)

    assert again["manager_trend"] == normalized["manager_trend"]

def test_manager_trend_does_not_break_receiving_max_constraint():
    payload = config()
    payload["manager_trend"] = {
        "enabled": True,
        "scores": [
            {"weekday": i, "morning": 0, "afternoon": 10000}
            for i in range(7)
        ],
    }

    option = generate_schedule(payload)["options"][0]
    manager = next(item for item in option["metrics"]["employees"] if item["employee_id"] == "phuong")

    assert manager["receiving"] <= 1

def test_normalize_requires_exactly_one_active_store_manager():
    payload = config()
    payload["employees"] = [{**employee, "role": "EMPLOYEE"} for employee in payload["employees"]]
    with pytest.raises(Exception, match="đúng 1 CHT"):
        normalize_config(payload)

    payload = config()
    payload["employees"][1]["role"] = "STORE_MANAGER"
    with pytest.raises(Exception, match="đúng 1 CHT"):
        normalize_config(payload)


def test_regional_manager_rules_are_canonical_and_cannot_be_removed_from_payload():
    payload = config()
    payload["fixed_weekday_rules"] = []

    normalized = normalize_config(payload)
    regional = [rule for rule in normalized["fixed_weekday_rules"] if rule.get("source") == "REGIONAL"]

    assert regional == [
        {"employee_id": "phuong", "weekday": 0, "shift": "MORNING", "level": "HARD", "source": "REGIONAL"},
        {"employee_id": "phuong", "weekday": 1, "shift": "AFTERNOON", "level": "HARD", "source": "REGIONAL"},
    ]


def test_missing_manager_trend_migrates_to_real_default_scores():
    payload = config()
    payload.pop("manager_trend", None)

    normalized = normalize_config(payload)
    monday = next(item for item in normalized["manager_trend"]["scores"] if item["weekday"] == 0)

    assert normalized["manager_trend"]["enabled"] is True
    assert monday == {"weekday": 0, "morning": 57, "afternoon": 66}


def test_manager_trend_objective_is_lexicographic_before_ordinary_soft_goals():
    payload = config()
    payload["receiving_days"] = []
    payload["employee_rules"] = [{
        "employee_id": "phuong",
        "target_morning": 3,
        "target_afternoon": 4,
        "receiving_min": 0,
        "receiving_target": None,
        "receiving_max": None,
    }]
    payload["manager_trend"] = _manager_trend_payload()

    option = generate_schedule(payload)["options"][0]

    assert isinstance(option["objective"], dict)
    assert set(option["objective"]) == {"staffing", "manager_target", "manager_trend", "soft"}
    rows = lookup(option["assignments"])
    assert rows[("phuong", "2026-09-16")]["shift"] == "MORNING"
    assert rows[("phuong", "2026-09-18")]["shift"] == "AFTERNOON"

