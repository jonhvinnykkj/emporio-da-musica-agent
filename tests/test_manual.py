from pathlib import Path

import pytest

from emporio.catalog import DataError
from emporio.manual import load_manual


@pytest.fixture(scope="module")
def manual_text(data_dir):
    return load_manual(data_dir / "politicas_da_loja.pdf")


def test_manual_keeps_tables_and_lines(manual_text):
    assert "Cartão de Crédito | Até 12x sem juros" in manual_text
    assert "Página 4" not in manual_text
    assert "Empório da Música Manual de Políticas e Procedimentos" not in manual_text


def test_errata_resolves_the_contradictions(manual_text):
    for fact in ("(67) 3341-4444", "(67) 3321-4500", "contato@emporiodamusica.com.br", "3.1"):
        assert fact in manual_text


def test_errata_comes_after_the_manual(manual_text):
    assert manual_text.index("ERRATA") > manual_text.index("3.1 Regras de Parcelamento")


def test_numbered_list_and_page_spanning_section_stay_whole(manual_text):
    assert "7.2 Fluxo de Atendimento Padrão" in manual_text
    assert "1. Saudação" in manual_text and "Fechamento" in manual_text


def test_missing_pdf_raises_data_error(tmp_path: Path):
    with pytest.raises(DataError):
        load_manual(tmp_path / "nope.pdf")
