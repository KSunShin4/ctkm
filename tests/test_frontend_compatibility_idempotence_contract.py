from pathlib import Path


def _source() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "frontend" / "src" / "main.jsx").read_text(encoding="utf-8")


def test_fetch_shim_uses_native_fetch_not_previous_wrapper():
    source = _source()
    assert "const COMPAT_KEY = '__ctkmCompatibilityV1'" in source
    assert "if (!compat.nativeFetch) compat.nativeFetch = window.fetch.bind(window)" in source
    assert "const nativeFetch = compat.nativeFetch" in source
    assert "window.fetch = compatibilityFetch" in source
    assert "compatibilityFetch.__ctkmCompatibilityFetchV1 = true" in source
    assert "const nativeFetch = window.fetch.bind(window)" not in source


def test_file_name_shim_reuses_the_native_descriptor():
    source = _source()
    assert "if (!compat.nativeFileNameDescriptor)" in source
    assert "compat.nativeFileNameDescriptor = Object.getOwnPropertyDescriptor(File.prototype, 'name')" in source
    assert "const fileNameDescriptor = compat.nativeFileNameDescriptor" in source


def test_hmr_reuses_react_root_and_replaces_observer():
    source = _source()
    assert "compat.labelObserver?.disconnect?.()" in source
    assert "compat.labelObserver = labelObserver" in source
    assert "if (!compat.reactRoot) compat.reactRoot = ReactDOM.createRoot(rootElement)" in source
    assert "compat.reactRoot.render(" in source
    assert "<UiPreferenceRoot>" in source
    assert "<App />" in source
    assert "ReactDOM.createRoot(rootElement).render(<App />)" not in source
