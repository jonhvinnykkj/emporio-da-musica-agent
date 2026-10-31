"""Store manual: PDF split by numbered section, plus notes resolving its contradictions."""

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

PAGE_NOISE = re.compile(r"^(Empório da Música Manual de Políticas e Procedimentos|Página \d+)$")
SUBSECTION = re.compile(r"^(\d+\.\d+)\s+(\S.*)$")
TOP_SECTION = re.compile(r"^(\d+)\.\s+([A-ZÀ-Ú][^:]*)$")
LIST_MARKER = re.compile(r"^(•|\d+\.)\s+")
COLUMN_GAP = re.compile(r"\s{2,}")

# The manual contradicts itself or leaves gaps in these places. Each note records the
# reading we adopted; the README lists the same decisions for the store to confirm.
SECTION_NOTES = {
    "1": "O catálogo atual é menor que os 300 instrumentos citados e não tem itens de sopro nem de "
         "cordas orquestrais. Não repita esse número; veja o catálogo nas instruções.",
    "1.2": "Canais oficiais: telefone (67) 3341-4444 e e-mail contato@emporiodamusica.com.br, sem acento.",
    "3": "A seção 3.1 é mais específica e prevalece sobre a coluna 'Parcela mínima' desta tabela.",
    "3.1": "Até 3x, a parcela não pode ficar abaixo de R$ 50,00. Valores calculados vêm de "
           "search_products e quote_order.",
    "4.1": "Só vale para compras online. A base não registra o canal; pedidos enviados com rastreio "
           "são tratados como online.",
    "4.2": "Do 31º ao 90º dia após o recebimento ainda vale a garantia legal (seção 8.1): não diga que "
           "a loja não tem responsabilidade, encaminhe à equipe.",
    "4.3": "O prazo de 7 dias é contado a partir do recebimento.",
    "5.1": "Só Campo Grande está confirmada como região metropolitana. Pedido de exatamente R$ 500,00 "
           "tem frete grátis.",
    "6.1": "Este é o calendário geral. Só vale a promoção que estiver ativa no sistema (list_promotions).",
    "7": "A seção cita o WhatsApp (67) 3321-4500, que diverge da seção 1.2. Informe só (67) 3341-4444.",
    "7.1": "Não há lojas parceiras cadastradas: não cite nomes de lojas.",
}


@dataclass
class Section:
    id: str
    title: str
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join([f"{self.id} {self.title}", *self.lines])


class PolicyManual:
    def __init__(self, pdf_path: Path):
        self.sections = _split_sections(_clean_lines(pdf_path))

    def contents(self) -> str:
        return "\n".join(f"- {section.id} {section.title}" for section in self.sections.values())

    def read(self, section_ids: list[str]) -> dict:
        found, missing = [], []
        for requested in section_ids:
            requested = requested.strip().rstrip(".")
            matches = [
                section for section in self.sections.values()
                if section.id == requested or section.id.startswith(f"{requested}.")
            ]
            found.extend(matches) if matches else missing.append(requested)
        unique = {section.id: section for section in found}.values()
        result = {"secoes": [self._render(section) for section in unique]}
        if missing:
            result["secoes_inexistentes"] = missing
        return result

    @staticmethod
    def _render(section: Section) -> str:
        note = SECTION_NOTES.get(section.id)
        return f"{section.text}\n[Nota interna: {note}]" if note else section.text


def _clean_lines(pdf_path: Path) -> list[str]:
    lines = []
    # Page 1 is the cover; its contact data is repeated in section 1.2.
    for page in PdfReader(pdf_path).pages[1:]:
        # Layout mode keeps lines and table columns; the default yields one word per line.
        for line in page.extract_text(extraction_mode="layout").splitlines():
            line = LIST_MARKER.sub(r"\1 ", line.strip())
            line = COLUMN_GAP.sub(" | ", line)
            if line and not PAGE_NOISE.match(line):
                lines.append(line)
    return lines


def _split_sections(lines: list[str]) -> dict[str, Section]:
    sections: dict[str, Section] = {}
    current: Section | None = None
    next_top = 1
    for line in lines:
        subsection = SUBSECTION.match(line)
        top = TOP_SECTION.match(line)
        if subsection and current and subsection.group(1).split(".")[0] == current.id.split(".")[0]:
            current = Section(subsection.group(1), subsection.group(2), [])
        elif top and int(top.group(1)) == next_top:
            # Requiring the next number skips the numbered list inside section 7.2.
            current = Section(top.group(1), top.group(2), [])
            next_top += 1
        elif current:
            current.lines.append(line)
            continue
        else:
            continue
        sections[current.id] = current
    return sections
