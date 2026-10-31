import pytest

from emporio.policies import PolicyManual


@pytest.fixture(scope="module")
def manual(data_dir):
    return PolicyManual(data_dir / "politicas_da_loja.pdf")


def test_finds_all_sections(manual):
    tops = [section_id for section_id in manual.sections if "." not in section_id]
    assert tops == [str(number) for number in range(1, 11)]
    assert {"3.1", "4.4", "5.3", "7.3", "8.3"} <= set(manual.sections)


def test_numbered_list_inside_section_7_is_not_a_section(manual):
    assert "1. Saudação" in manual.sections["7.2"].text
    assert manual.sections["1"].title == "Sobre a Empório da Música"


def test_section_spanning_two_pages_stays_whole(manual):
    text = manual.sections["7.2"].text
    assert "Saudação" in text and "Fechamento" in text
    assert "Página" not in text


def test_reading_a_parent_returns_its_subsections(manual):
    text = "\n".join(manual.read(["4"])["secoes"])
    assert "Trocas por Defeito" in text and "Itens Não Elegíveis" in text


def test_reading_a_subsection_returns_only_it(manual):
    text = "\n".join(manual.read(["4.2"])["secoes"])
    assert "Trocas por Defeito" in text and "Trocas por Preferência" not in text


def test_notes_are_attached(manual):
    assert "(67) 3341-4444" in manual.read(["1.2"])["secoes"][0]
    assert "Nota interna" in manual.read(["4.2"])["secoes"][0]


def test_unknown_section_is_reported(manual):
    assert manual.read(["99"]) == {"secoes": [], "secoes_inexistentes": ["99"]}


def test_contents_lists_titles(manual):
    assert "4.1 Direito de Arrependimento" in manual.contents()
