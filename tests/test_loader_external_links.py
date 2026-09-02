import importlib.util
from pathlib import Path
import sys


def _loader_module():
    root = Path(__file__).resolve().parents[1]
    modules_dir = root / "modules"
    if "modules" not in sys.modules:
        import types
        pkg = types.ModuleType("modules")
        pkg.__path__ = [str(modules_dir)]
        sys.modules["modules"] = pkg

    config_spec = importlib.util.spec_from_file_location(
        "modules.config_loader", modules_dir / "config_loader.py"
    )
    config_module = importlib.util.module_from_spec(config_spec)
    sys.modules[config_spec.name] = config_module
    config_spec.loader.exec_module(config_module)

    spec = importlib.util.spec_from_file_location("modules.loader_external_link_test", modules_dir / "1_loader.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_loader_disables_external_link_parsing(tmp_path, monkeypatch):
    from openpyxl import Workbook
    import openpyxl

    loader = _loader_module()
    source = tmp_path / "pog.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Export"
    sheet.append(["STOREID", "POGCODE", "ITEMID", "LOCATIONID"])
    sheet.append(["S1", "POG1", "P1", 1])
    workbook.save(source)

    real_load_workbook = openpyxl.load_workbook
    calls = []

    def recording_load_workbook(*args, **kwargs):
        calls.append(dict(kwargs))
        return real_load_workbook(*args, **kwargs)

    monkeypatch.setattr(openpyxl, "load_workbook", recording_load_workbook)

    loaded = loader.load_workbook_raw(str(source), is_pog_file=True, selected_sheet_names=["Export"])

    assert "Export" in loaded.sheets
    assert len(loaded.sheets["Export"].df) == 1
    assert calls
    assert calls[0].get("keep_links") is False
