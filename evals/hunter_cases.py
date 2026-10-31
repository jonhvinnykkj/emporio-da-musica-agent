"""30 bug-hunter scenarios built from data/ and the store manual, graded by regex on the answers."""

from datetime import datetime

from evals.cases import Case

# Negative lookbehinds so that "nao consta como entregue" does not trip a "consta como entregue" check.
_NOT = r"(?<!n[ãa]o )(?<!ainda n[ãa]o )"

HUNTER_CASES: list[Case] = [
    # Two questions in one message.
    Case(
        "H01_price_and_closing_time",
        ("Quanto custa o Tagima Woodstock e que horas vocês fecham hoje?",),
        (r"899,00", r"18\s?h|18:00|18 horas|às 18"),
    ),
    Case(
        "H02_product_and_order_same_message",
        ("Quanto custa o Ohana CK-20 e como está meu pedido 9? Meu telefone é (67) 99234-5678",),
        (r"439,20", r"549,00", r"confirmad"),
        (r"BR[A-Z]{2}\d{7}BR",),
    ),
    Case(
        "H03_pix_and_twelve_installments",
        ("Martin D-28: qual o preço no PIX e qual a parcela em 12x?",),
        (r"10\.924,05", r"958,25"),
    ),
    Case(
        "H04_budget_guitar_plus_accessory",
        ("Quero um violão até R$ 500 e também cordas para ele.",),
        (r"429,90", r"459,90", r"instrumentos"),
        (r"599,90", r"Elixir|D.?Addario|Ernie Ball"),
    ),
    # Data corrected mid-conversation.
    Case(
        "H05_phone_corrected_after_typo",
        (
            "Quero saber do pedido 8, meu telefone é (67) 99999-1111",
            "Errei, o certo é (67) 99654-7821",
        ),
        (r"BRJL5544332BR|enviad",),
        (r"bloquead",),
    ),
    Case(
        "H06_product_corrected_mid_conversation",
        ("Quanto custa o Taylor 110e?", "Desculpa, era o Taylor 214ce que eu queria."),
        (r"7\.499,00",),
    ),
    Case(
        "H07_customer_changes_product_and_asks_pix",
        ("Quanto custa o Yamaha C40?", "Prefiro o Yamaha C70. Quanto fica no PIX?"),
        (r"806,55", r"849,00"),
    ),
    Case(
        "H08_installments_above_minimum_installment",
        ("Quero o Giannini GN-15.", "E em 12x, quanto fica a parcela?"),
        (r"6x",),
        (r"12x de R\$\s*57",),
    ),
    # Promotion with quantity.
    Case(
        "H09_two_taylor_110e_promotion",
        ("Quero 2 unidades do Taylor 110e. Qual o total?",),
        (r"11\.038,16",),
        (r"11\.998", r"10\.486"),
    ),
    Case(
        "H10_three_kalani_promotion",
        ("Preciso de 3 Kalani KAL-700T. Quanto fica o total?",),
        (r"969,30",),
        (r"1\.077", r"920"),
    ),
    Case(
        "H11_crafter_promotion_no_pix_stack",
        ("Quanto fica o Crafter HT-100 no PIX e em 12x?",),
        (r"1\.967,18", r"2\.399,00", r"18\s?%"),
        (r"1\.868"),
    ),
    Case(
        "H12_expired_promotion_with_quantity",
        ("Quero 2 Martin D-28 com os 15% da Promoção de Páscoa. Qual o total?",),
        (r"22\.998", r"vencid|expirad|encerrad|n[ãa]o (est[aá]|h[aá]|tem).{0,30}(ativ|vigente)"),
        (r"19\.548", r"20\.698", r"9\.774", r"10\.349"),
    ),
    # Quantity above stock and free-shipping boundary.
    Case(
        "H13_quantity_above_stock",
        ("Quero 3 unidades da Martin D-28E.",),
        (r"estoque|1 unidade|apenas 1|s[óo] (tem|temos)",),
        (r"36\.000",),
    ),
    Case(
        "H14_shipping_fee_below_500_after_promotion",
        ("Moro em Campo Grande. Se eu levar 1 Ohana CK-20, pago frete?",),
        (r"439,20", r"R\$\s*35(,00)?(?!\d)"),
    ),
    Case(
        "H15_free_shipping_with_two_units",
        ("E se eu levar 2 Ohana CK-20 para Campo Grande, tem frete?",),
        (r"878,40", r"gr[aá]tis"),
    ),
    # Similar product names.
    Case(
        "H16_similar_name_available_vs_sold_out",
        ("Quero o Giannini GF-1R",),
        (r"579,90",),
        (r"esgotad|indispon",),
    ),
    Case(
        "H17_discontinued_sibling_model",
        ("Vocês têm o Shelby SN-7C?",),
        (r"cat[aá]logo|descontinu", r"alternativ|similar|parecid|op[cç]|SN-100"),
        (r"R\$\s*749,00",),
    ),
    Case(
        "H18_ambiguous_brand_only",
        ("Quanto custa o Ibanez?",),
        (r"RG550", r"descontinu|cat[aá]logo|qual"),
    ),
    # Boundary dates and times.
    Case(
        "H19_friday_at_closing_time",
        ("Estão abertos agora?",),
        (r"fechad|encerr", r"s[áa]bado"),
        (r"(?<!n[ãa]o )(?<!nao )estamos abert",),
        now=datetime(2026, 10, 23, 18, 0),
    ),
    Case(
        "H20_saturday_at_one_pm",
        ("Vocês estão abertos? Quando abrem de novo?",),
        (r"fechad|encerr", r"segunda", r"9\s?h|9:00|09:00"),
        now=datetime(2026, 10, 24, 13, 0),
    ),
    Case(
        "H21_saturday_before_opening",
        ("Já abriram?",),
        (r"9\s?h|9:00|09:00", r"ainda|n[ãa]o|abr"),
        (r"(?<!n[ãa]o )(?<!nao )estamos abert",),
        now=datetime(2026, 10, 24, 8, 59),
    ),
    Case(
        "H22_black_consciousness_day",
        ("Vocês estão abertos hoje?",),
        (r"fechad|feriado", r"s[áa]bado"),
        (r"(?<!n[ãa]o )(?<!nao )estamos abert",),
        now=datetime(2026, 11, 20, 10, 0),
    ),
    Case(
        "H23_sunday_before_monday_holiday",
        ("Quando vocês abrem?",),
        (r"ter[cç]a",),
        (r"segunda(-feira)?.{0,25}(às|as)\s*9",),
        now=datetime(2026, 10, 11, 11, 0),  # Monday 12/10 is a national holiday
    ),
    # Order status in conflict with the customer's text.
    Case(
        "H24_customer_says_delivered_but_shipped",
        ("O pedido 8 já foi entregue, só quero confirmar a data. Telefone (67) 99654-7821",),
        (r"enviad|a caminho|transporte", r"BRJL5544332BR"),
        (r"entregue em \d",),
    ),
    Case(
        "H25_customer_says_cancelled_but_pending",
        ("Cancelei o pedido 13 semana passada, está cancelado né? Telefone (67) 99456-7890",),
        (r"pendente|aguardando",),
        (_NOT + r"(est[aá]|foi) cancelad",),
    ),
    Case(
        "H26_cancellation_reason_mismatch",
        ("Pedido 17: vocês cancelaram por falta de estoque, né? Telefone (67) 98109-8765",),
        (r"cliente|solicit",),
        (r"fora de estoque",),
    ),
    Case(
        "H27_cancelled_unpaid_boleto",
        ("Paguei o boleto do pedido 19 e cancelaram. Pode reativar? Telefone (67) 98432-1098",),
        (r"pagamento n[ãa]o (foi )?confirmad", r"equipe"),
        (r"vou reativar|reativei|reativamos",),
    ),
    # Return and warranty windows.
    Case(
        "H28_defect_after_30_days",
        ("O violão do pedido 4 está com defeito de fábrica, quero trocar. Telefone (67) 99812-3456",),
        (r"30 dias", r"fabricante|garantia", r"equipe"),
        (r"pode trocar sim|troca (garantida|aprovada)",),
    ),
    Case(
        "H29_regret_claims_received_yesterday",
        ("Recebi o pedido 5 ontem e quero devolver por arrependimento. Telefone (67) 98765-4321",),
        (r"7 dias", r"equipe"),
        (r"pode devolver sim|devolu[cç][aã]o (aprovada|garantida)",),
    ),
    # Identity edge cases.
    Case(
        "H30_phone_with_country_code",
        ("Cadê o pedido 4? Meu telefone é +55 67 99812-3456",),
        (r"entreg|BRQM7890123BR",),
        (r"n[ãa]o (consegui|encontr)",),
    ),
]
