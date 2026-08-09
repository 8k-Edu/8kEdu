"""Any handler test that reaches a widget-saving path would otherwise write into the repo's
own data/ dir, so every test gets a throwaway store root unless it patches one itself."""
import pytest

from agent import widget_store


@pytest.fixture(autouse=True)
def isolated_widget_store(monkeypatch, tmp_path):
    monkeypatch.setattr(widget_store, "DATA", tmp_path / "data")
