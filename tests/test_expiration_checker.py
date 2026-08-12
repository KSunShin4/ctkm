import importlib.util
from pathlib import Path

import pandas as pd

MODULE = Path(__file__).parents[1] / "modules" / "11_expiration_checker.py"
spec = importlib.util.spec_from_file_location("expiration_checker", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_check_entries_reports_each_kind_of_result():
    frame = pd.DataFrame({
        "ITEMID": ["P29352", "P29352"],
        "BATCHNUMER": ["00526", "OTHER"],
        "EXPDATE": ["18/03/2029", "01/01/2030"],
    })
    result = mod.check_entries(frame, "\n".join([
        "p29352;00526;18/03/2029",
        "P29352;BAD;18/03/2029",
        "P29352;00526;19/03/2029",
        "P00000;1;01/01/2030",
        "broken",
    ]))
    assert [row["status"] for row in result] == [
        "matched", "batch_mismatch", "date_mismatch", "not_found", "invalid"
    ]
    assert result[0]["normalized"] == "P29352;00526;18/03/2029"
    assert [row["exp_date"] for row in result[0]["related_rows"]] == ["01/01/2030", "18/03/2029"]
    assert result[0]["related_rows"][0]["batch_number"] == "OTHER"
