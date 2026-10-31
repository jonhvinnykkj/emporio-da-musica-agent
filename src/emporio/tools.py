"""Tools the model can call. Each one is a narrow, typed door to the store's data."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from emporio.catalog import AVAILABLE, Catalog, normalize
from emporio.journal import Journal
from emporio.manual import load_manual
from emporio.orders import OrderBook
from emporio.pricing import brl, installment_text, metro_shipping

MAX_FAILED_CHECKS = 3
SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 15
COMPLAINT_RETURN_TIME = "24 horas úteis"
COMBINED_PAYMENT_ABOVE = Decimal("2000")
HANDOFF_REASONS = ["reclamacao", "atendente", "sem_resposta", "aprovacao", "identidade", "outro"]
NOT_VERIFIED = {
    "verificado": False,
    "mensagem": "Não foi possível localizar o pedido com esses dados. Peça ao cliente para conferir o número e o telefone.",
}
LOCKED = {
    "verificado": False,
    "bloqueado": True,
    "mensagem": "Muitas tentativas sem sucesso. Não tente de novo: encaminhe para a equipe com encaminhar_para_equipe.",
}


def tool_definitions(category_names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": "buscar_produtos",
            "description": (
                "Busca instrumentos no sistema e devolve disponibilidade, preço atual, promoção ativa, preço no PIX, "
                "parcelamento e especificações. Use para qualquer pergunta sobre produto, preço, estoque ou promoção. "
                "Mostra 5 itens, ou mais com 'limite', e informa o total encontrado. Itens indisponíveis que batem com "
                "a busca vêm em 'indisponiveis', com sugestões em 'alternativas'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "consulta": {
                        "type": "string",
                        "description": (
                            "As palavras do cliente sobre o item: marca, modelo, tamanho, cor ou uso. Os filtros não "
                            "enxergam nada disso, então preencha sempre que ele disser mais que a categoria. "
                            "Ex.: 'takamine gd20', 'ukulele concert', 'sunburst', 'iniciante', 'choro'."
                        ),
                    },
                    "categoria": {"type": "string", "enum": category_names},
                    "preco_minimo": {"type": "number", "description": "Preço mínimo em reais."},
                    "preco_maximo": {"type": "number", "description": "Preço máximo em reais."},
                    "cordas": {
                        "type": "string",
                        "enum": ["nylon", "aco"],
                        "description": "Tipo de corda de violões e ukuleles.",
                    },
                    "eletrico": {
                        "type": "boolean",
                        "description": "true para eletroacústico, false para acústico.",
                    },
                    "somente_promocao": {
                        "type": "boolean",
                        "description": "true para listar só itens com promoção ativa.",
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Quantos itens mostrar: 5 por padrão, até 15. Use 15 para listar todas as opções.",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "calcular_compra",
            "description": (
                "Calcula o valor de uma compra: subtotal, total no PIX, parcelamento e frete. Use sempre que houver "
                "quantidade maior que 1, mais de um produto ou frete. Os ids vêm de buscar_produtos."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "itens": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "produto_id": {"type": "integer"},
                                "quantidade": {"type": "integer"},
                            },
                            "required": ["produto_id", "quantidade"],
                            "additionalProperties": False,
                        },
                    },
                    "cidade": {"type": "string", "description": "Cidade de entrega, se o cliente informou."},
                },
                "required": ["itens"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "consultar_pedido",
            "description": (
                "Consulta status, itens, rastreio e previsão de um pedido. Exige o número do pedido e o telefone "
                "cadastrado, ambos informados pelo cliente nesta conversa. E-mail não identifica ninguém."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "numero_pedido": {"type": "integer"},
                    "telefone": {"type": "string", "description": "Telefone informado pelo cliente."},
                },
                "required": ["numero_pedido", "telefone"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "encaminhar_para_equipe",
            "description": (
                "Registra o caso para a equipe humana, que retorna ao cliente. Use para reclamações, pedidos de "
                "atendente, casos sem resposta no manual, trocas e devoluções que precisam de aprovação e quando a "
                "identidade do cliente não pôde ser confirmada."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "motivo": {"type": "string", "enum": HANDOFF_REASONS},
                    "resumo": {"type": "string", "description": "Resumo objetivo do caso para a equipe."},
                    "telefone": {"type": "string", "description": "Telefone do cliente, se informado."},
                    "numero_pedido": {"type": "integer"},
                },
                "required": ["motivo", "resumo"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


@dataclass(frozen=True)
class StoreData:
    catalog: Catalog
    orders: OrderBook
    manual: str

    @classmethod
    def load(cls, data_dir: Path) -> "StoreData":
        catalog = Catalog(data_dir)
        return cls(catalog, OrderBook(data_dir, catalog), load_manual(data_dir / "politicas_da_loja.pdf"))


class Toolbox:
    """The four tools for one conversation. Nothing here writes to the store's data."""

    def __init__(self, data: StoreData, journal: Journal, session_id: str, clock: Callable[[], datetime]):
        self.data = data
        self.journal = journal
        self.session_id = session_id
        self.clock = clock
        self.failed_checks = 0
        self.handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "buscar_produtos": self.search_products,
            "calcular_compra": self.quote_purchase,
            "consultar_pedido": self.look_up_order,
            "encaminhar_para_equipe": self.hand_off,
        }

    def run(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Return the JSON result and whether it is an error the model should see."""
        handler = self.handlers.get(name)
        if handler is None:
            return json.dumps({"erro": f"Ferramenta desconhecida: {name}"}, ensure_ascii=False), True
        try:
            return json.dumps(handler(**arguments), ensure_ascii=False), False
        except (TypeError, ValueError, KeyError) as error:
            return json.dumps({"erro": f"Parâmetros inválidos: {error}"}, ensure_ascii=False), True

    def search_products(
        self,
        consulta: str | None = None,
        categoria: str | None = None,
        preco_minimo: float | None = None,
        preco_maximo: float | None = None,
        cordas: str | None = None,
        eletrico: bool | None = None,
        somente_promocao: bool = False,
        limite: int = SEARCH_LIMIT,
    ) -> dict[str, Any]:
        return self.data.catalog.search(
            query=consulta,
            category=categoria,
            min_price=preco_minimo,
            max_price=preco_maximo,
            strings=cordas,
            electronics=eletrico,
            on_sale=somente_promocao,
            limit=max(1, min(limite, MAX_SEARCH_LIMIT)),
        )

    def look_up_order(self, numero_pedido: int, telefone: str) -> dict[str, Any]:
        """Same answer for a wrong phone and a missing order, so numbers cannot be probed."""
        if self.failed_checks >= MAX_FAILED_CHECKS:
            return LOCKED
        order = self.data.orders.verified_order(numero_pedido, telefone)
        if order is None:
            self.failed_checks += 1
            return LOCKED if self.failed_checks >= MAX_FAILED_CHECKS else NOT_VERIFIED
        return {"verificado": True} | self.data.orders.view(order, self.clock().date())

    def quote_purchase(self, itens: list[dict[str, Any]], cidade: str | None = None) -> dict[str, Any]:
        wanted: dict[int, int] = {}
        for item in itens:
            wanted[item["produto_id"]] = wanted.get(item["produto_id"], 0) + item["quantidade"]
        lines, problems = [], []
        subtotal = pix_total = Decimal("0")
        for product_id, quantity in wanted.items():
            product = self.data.catalog.products.get(product_id)
            if product is None or product.availability != AVAILABLE:
                problems.append(f"Produto {product_id} não está disponível para venda.")
            elif quantity < 1 or quantity > product.stock:
                problems.append(f"{product.name}: quantidade pedida {quantity}, estoque {product.stock}.")
            else:
                line_total = product.quote.price * quantity
                subtotal += line_total
                pix_total += product.quote.pix_total(quantity)
                lines.append(
                    {
                        "produto": product.name,
                        "quantidade": quantity,
                        "preco_unitario": brl(product.quote.price),
                        "total": brl(line_total),
                    }
                )
        result: dict[str, Any] = {"itens": lines, "problemas": problems}
        if not lines:
            return result
        result |= {
            "subtotal": brl(subtotal),
            "total_no_pix": brl(pix_total),
            "observacao_pix": "O desconto de PIX vale só para itens fora de promoção.",
            "parcelamento": installment_text(subtotal),
            "pode_combinar_formas_de_pagamento": subtotal > COMBINED_PAYMENT_ABOVE,
        }
        return result | _shipping(subtotal, pix_total, cidade)

    def hand_off(
        self, motivo: str, resumo: str, telefone: str | None = None, numero_pedido: int | None = None
    ) -> dict[str, Any]:
        if motivo not in HANDOFF_REASONS:
            raise ValueError(f"motivo desconhecido: {motivo}")
        self.journal.record(
            "encaminhamento",
            self.session_id,
            {"motivo": motivo, "resumo": resumo, "telefone": telefone, "numero_pedido": numero_pedido},
        )
        result = {"encaminhado": True, "encaminhado_para": "equipe de atendimento"}
        if motivo == "reclamacao":
            result["prazo_de_retorno"] = COMPLAINT_RETURN_TIME
        return result


def _is_campo_grande(city: str) -> bool:
    """Accept 'Campo Grande', '... - MS', '.../MS' and 'campo grande ms'; nothing else."""
    return normalize(city) in {"campo grande", "campo grande ms"}


def _shipping(subtotal: Decimal, pix_total: Decimal, city: str | None) -> dict[str, Any]:
    if city is None:
        return {"frete": "Depende da cidade de entrega."}
    if not _is_campo_grande(city):
        return {"frete": "Calculado pelo CEP de destino. Itens grandes podem exigir cotação individual."}
    fee = metro_shipping(subtotal)
    return {
        "frete": brl(fee) if fee else "Grátis",
        "total_com_frete": brl(subtotal + fee),
        "total_no_pix_com_frete": brl(pix_total + fee),
        "prazo_de_entrega": "1 a 3 dias úteis",
    }
