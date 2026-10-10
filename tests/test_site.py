"""Abre cada página do site (sem navegador) e confere que nenhuma dá erro."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "app"
PAGINAS = sorted(p.name for p in (APP / "paginas").glob("*.py"))


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_abre_sem_erro(pagina):
    app = AppTest.from_file(str(APP / "site.py"), default_timeout=60)
    app.run()
    app.switch_page(f"paginas/{pagina}").run()
    assert not app.exception, [e.message for e in app.exception]
