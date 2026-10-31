"""Tools the model can call. Each one is a narrow, typed door to the store's data."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio.catalog import AVAILABLE, Catalog, normalize
from emporio.orders import OrderBook
from emporio.policies import PolicyManual
from emporio.pricing import brl, installment_text, metro_shipping
from emporio.store import Store

MAX_FAILED_CHECKS = 3
COMPLAINT_RETURN_TIME = "24 horas úteis"
COMBINED_PAYMENT_ABOVE = Decimal("2000")
TICKET_KINDS = [
    "reclamacao",
    "cancelamento",
    "troca_ou_devolucao",
    "garantia",
    "atraso",
    "privacidade",
    "duvida",
    "atendente",
]
NOT_VERIFIED = {
    "verificado": False,
    "mensagem": "Não foi possível localizar o pedido com esses dados. Peça ao cliente para conferir o número e o contato.",
}
LOCKED = {
    "verificado": False,
    "mensagem": "Muitas tentativas sem sucesso. Não tente de novo: encaminhe para a equipe com open_ticket.",
}


def tool_definitions(category_names: list[str]) -> list[dict]:
    return [
        {
            "name": "search_products",
            "description": (
                "Busca instrumentos no sistema e devolve disponibilidade, preço atual, promoção ativa, preço no PIX, "
                "parcelamento e especificações. Use para qualquer pergunta sobre produto, preço ou estoque. Itens "
                "indisponíveis que batem com a busca vêm em 'indisponiveis', com sugestões em 'alternativas'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Marca, modelo ou característica. Ex.: 'takamine gd20', 'iniciante', 'choro'.",
                    },
                    "category": {"type": "string", "enum": category_names},
                    "min_price": {"type": "number", "description": "Preço mínimo em reais."},
                    "max_price": {"type": "number", "description": "Preço máximo em reais."},
                    "strings": {
                        "type": "string",
                        "enum": ["nylon", "aco"],
                        "description": "Tipo de corda de violões e ukuleles.",
                    },
                    "electronics": {
                        "type": "boolean",
                        "description": "true para eletroacústico, false para acústico.",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "list_promotions",
            "description": (
                "Lista as promoções ativas no sistema. Se o cliente citar uma campanha, passe o nome em 'query': "
                "'campanhas_encerradas' indica que ela não está mais valendo."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Nome da campanha ou do produto."}},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "quote_order",
            "description": (
                "Calcula o valor de uma compra: subtotal, total no PIX, parcelamento e frete. Use sempre que houver "
                "quantidade maior que 1, mais de um produto ou frete. Os ids vêm de search_products."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "integer"},
                                "quantity": {"type": "integer"},
                            },
                            "required": ["product_id", "quantity"],
                            "additionalProperties": False,
                        },
                    },
                    "city": {"type": "string", "description": "Cidade de entrega, se o cliente informou."},
                },
                "required": ["items"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "get_order",
            "description": (
                "Consulta status, itens, rastreio e previsão de um pedido. Exige o número do pedido e o telefone ou "
                "e-mail cadastrado, ambos informados pelo cliente nesta conversa."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer"},
                    "contact": {
                        "type": "string",
                        "description": "Telefone ou e-mail informado pelo cliente.",
                    },
                },
                "required": ["order_id", "contact"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "check_return",
            "description": (
                "Verifica se um pedido pode ser devolvido ou trocado e calcula os prazos exatos. Use em todo pedido de "
                "devolução, troca ou garantia ligado a um pedido. Exige número do pedido e telefone ou e-mail cadastrado."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer"},
                    "contact": {"type": "string"},
                    "reason": {"type": "string", "enum": ["arrependimento", "defeito", "preferencia"]},
                },
                "required": ["order_id", "contact", "reason"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "read_policy",
            "description": (
                "Lê seções do manual da loja. Use para horários, endereço, pagamento, parcelamento, trocas, frete, "
                "promoções, garantia e privacidade. Passe os números do sumário; '4' traz também 4.1, 4.2 etc."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"sections": {"type": "array", "items": {"type": "string"}}},
                "required": ["sections"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "name": "open_ticket",
            "description": (
                "Registra um chamado para a equipe humana e devolve o protocolo. Use para reclamações, cancelamentos, "
                "atrasos, casos sem regra no manual, pedidos de exclusão de dados e quando o cliente pedir um atendente."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": TICKET_KINDS},
                    "summary": {"type": "string", "description": "Resumo objetivo do caso para a equipe."},
                    "contact": {"type": "string", "description": "Contato do cliente, se informado."},
                    "order_id": {"type": "integer"},
                },
                "required": ["kind", "summary"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


@dataclass(frozen=True)
class StoreData:
    catalog: Catalog
    orders: OrderBook
    manual: PolicyManual

    @classmethod
    def load(cls, data_dir: Path) -> "StoreData":
        catalog = Catalog(data_dir)
        return cls(catalog, OrderBook(data_dir, catalog), PolicyManual(data_dir / "politicas_da_loja.pdf"))


class Toolbox:
    def __init__(self, data: StoreData, store: Store, session_id: str, today: date):
        self.data = data
        self.store = store
        self.session_id = session_id
        self.today = today
        self.handlers = {
            "search_products": self.data.catalog.search,
            "list_promotions": self.data.catalog.promotions_report,
            "quote_order": self.quote_order,
            "get_order": self.get_order,
            "check_return": self.check_return,
            "read_policy": lambda sections: self.data.manual.read(sections),
            "open_ticket": self.open_ticket,
        }

    def run(self, name: str, arguments: dict) -> tuple[str, bool]:
        """Return the JSON result and whether it is an error the model should see."""
        handler = self.handlers.get(name)
        if handler is None:
            return json.dumps({"erro": f"Ferramenta desconhecida: {name}"}, ensure_ascii=False), True
        try:
            return json.dumps(handler(**arguments), ensure_ascii=False), False
        except (TypeError, ValueError, KeyError) as error:
            return json.dumps({"erro": f"Parâmetros inválidos: {error}"}, ensure_ascii=False), True

    def _verified(self, order_id: int, contact: str):
        """Same answer for a wrong contact and a missing order, so numbers cannot be probed."""
        if self.store.failed_checks(self.session_id) >= MAX_FAILED_CHECKS:
            return None, LOCKED
        order = self.data.orders.verified_order(order_id, contact)
        if order is None:
            self.store.record_failed_check(self.session_id)
            return None, NOT_VERIFIED
        return order, None

    def get_order(self, order_id: int, contact: str) -> dict:
        order, refusal = self._verified(order_id, contact)
        return refusal or {"verificado": True} | self.data.orders.view(order, self.today)

    def check_return(self, order_id: int, contact: str, reason: str) -> dict:
        order, refusal = self._verified(order_id, contact)
        return refusal or {"verificado": True} | self.data.orders.return_decision(order, reason, self.today)

    def quote_order(self, items: list[dict], city: str | None = None) -> dict:
        lines, problems = [], []
        subtotal = pix_total = Decimal("0")
        for item in items:
            product = self.data.catalog.products.get(item["product_id"])
            quantity = item["quantity"]
            if product is None or product.availability != AVAILABLE:
                problems.append(f"Produto {item['product_id']} não está disponível para venda.")
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
        result = {"itens": lines, "problemas": problems}
        if not lines:
            return result
        result |= {
            "subtotal": brl(subtotal),
            "total_no_pix": brl(pix_total),
            "observacao_pix": "O desconto de PIX vale só para itens fora de promoção.",
            "parcelamento": installment_text(subtotal),
            "pode_combinar_formas_de_pagamento": subtotal > COMBINED_PAYMENT_ABOVE,
        }
        return result | _shipping(subtotal, pix_total, city)

    def open_ticket(
        self, kind: str, summary: str, contact: str | None = None, order_id: int | None = None
    ) -> dict:
        protocol = self.store.create_ticket(self.session_id, kind, summary, contact, order_id)
        result = {"protocolo": protocol, "encaminhado_para": "equipe de atendimento"}
        if kind == "reclamacao":
            result["prazo_de_retorno"] = COMPLAINT_RETURN_TIME
        return result


def _shipping(subtotal: Decimal, pix_total: Decimal, city: str | None) -> dict:
    if city is None:
        return {"frete": "Depende da cidade de entrega."}
    if normalize(city) != "campo grande":
        return {"frete": "Calculado pelo CEP de destino. Itens grandes podem exigir cotação individual."}
    fee = metro_shipping(subtotal)
    return {
        "frete": brl(fee) if fee else "Grátis",
        "total_com_frete": brl(subtotal + fee),
        "total_no_pix_com_frete": brl(pix_total + fee),
        "prazo_de_entrega": "1 a 3 dias úteis",
    }
