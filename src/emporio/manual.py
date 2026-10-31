"""Store manual as plain text for the fixed context, followed by notes resolving its contradictions."""

import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from emporio.catalog import DataError

PAGE_NOISE = re.compile(r"^(Empório da Música Manual de Políticas e Procedimentos|Página \d+)$")
LIST_MARKER = re.compile(r"^(•|\d+\.)\s+")
COLUMN_GAP = re.compile(r"\s{2,}")

# The manual contradicts itself or leaves gaps in these places. Each line records the
# reading we adopted; the README lists the same decisions for the store to confirm.
ERRATA = """ERRATA (valem sobre o texto acima)
- Telefone: (67) 3341-4444. WhatsApp: (67) 3321-4500. E-mail: contato@emporiodamusica.com.br, sem acento.
- Parcelamento: a seção 3.1 prevalece sobre a coluna "Parcela mínima" da tabela da seção 3. Até 3x a parcela mínima é R$ 50,00; de 4x a 6x, R$ 80,00; de 7x a 12x, R$ 100,00.
- Os 30 dias da seção 4.2 (troca por defeito) e os 90 dias da seção 8.1 (garantia legal) são prazos diferentes. Depois dos 30 dias, não diga que a loja não tem responsabilidade: encaminhe à equipe.
- Não há lojas parceiras cadastradas. Não cite nomes de lojas.
- O catálogo atual é menor que os 300 instrumentos citados e não tem itens de sopro nem de cordas orquestrais. Não repita esse número."""


def load_manual(pdf_path: Path) -> str:
    """Manual text with page headers removed and table columns joined by ' | ', plus the errata."""
    try:
        pages = PdfReader(pdf_path).pages
        # Page 1 is the cover; its contact data is repeated in section 1.2.
        # Layout mode keeps lines and table columns; the default yields one word per line.
        raw_lines = [
            line for page in pages[1:] for line in page.extract_text(extraction_mode="layout").splitlines()
        ]
    except (FileNotFoundError, PyPdfError) as error:
        raise DataError(f"{pdf_path.name}: cannot read the manual ({error})") from error
    lines = []
    for raw in raw_lines:
        line = COLUMN_GAP.sub(" | ", LIST_MARKER.sub(r"\1 ", raw.strip()))
        if line and not PAGE_NOISE.match(line):
            lines.append(line)
    return "\n".join([*lines, "", ERRATA])
