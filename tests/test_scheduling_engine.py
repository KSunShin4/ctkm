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


def test_off_shortage_stays_one_shift_per_day_and_is_reported_as_warning():
    payload = config()
    payload["requests"] = [{"employee_id": "mi", "date": "2026-09-16", "type": "OFF"}]

    option = generate_schedule(payload)["options"][0]
    rows = lookup(option["assignments"])

    assert len(rows) == 35
    assert rows[("mi", "2026-09-16")]["shift"] == "OFF"
    assert option["status"] == "VALID_WITH_WARNINGS"
    assert any("thiếu" in warning.lower() for warning in option["warnings"])


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