"""Arbitrary inputs: the rules must hold for text nobody thought to try."""

import json
from datetime import date, datetime

from hypothesis import example, given, settings
from hypothesis import strategies as st

from emporio.guardrails import amounts_in
from emporio.hours import describe
from emporio.journal import mask_contact
from emporio.orders import digits_of
from emporio.tools import Toolbox
from fakes import MemoryJournal

NOW = datetime(2026, 10, 28, 14, 0)

json_scalars = st.none() | st.booleans() | st.integers() | st.floats() | st.text()
json_values = st.recursive(
    json_scalars, lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.text(), inner, max_size=3)
)
TOOL_NAMES = (
    st.sampled_from(["buscar_produtos", "calcular_compra", "consultar_pedido", "encaminhar_para_equipe"])
    | st.text()
)
ARGUMENT_NAMES = st.sampled_from(
    ["consulta", "categoria", "preco_minimo", "preco_maximo", "cordas", "eletrico", "itens", "cidade"]
    + ["numero_pedido", "telefone", "motivo", "resumo", "somente_promocao"]
) | st.text(max_size=8)


@given(text=st.text())
def test_search_never_raises_and_always_reports_the_total(catalog, text):
    result = catalog.search(query=text)
    assert isinstance(result["total_encontrado"], int)
    assert len(result["produtos"]) <= 5


@given(order_id=st.integers(), phone=st.text())
def test_verified_order_never_raises_nor_opens_without_the_real_phone(book, order_id, phone):
    order = book.verified_order(order_id, phone)
    if order is not None:
        on_file = digits_of(book.customers[order.customer_id]["phone"])
        assert digits_of(phone).endswith(on_file[-9:])


@given(order_id=st.sampled_from([1, 8, 12]), phone=st.text(alphabet="0123456789 +()-", max_size=20))
def test_phone_with_digits_and_separators_needs_the_whole_number(book, order_id, phone):
    order = book.verified_order(order_id, phone)
    if order is not None:
        assert len(digits_of(phone)) >= 9


@given(text=st.text())
def test_amounts_in_never_raises(text):
    amounts_in(text)


@given(text=st.from_regex(r"R\$ ?[0-9.,]{0,30}", fullmatch=True))
def test_amounts_in_survives_money_shaped_noise(text):
    amounts_in(text)


@given(name=TOOL_NAMES, arguments=st.dictionaries(ARGUMENT_NAMES, json_values, max_size=5))
@example(name="buscar_produtos", arguments={"preco_minimo": []})
@example(name="buscar_produtos", arguments={"preco_maximo": float("nan")})
@settings(max_examples=300)
def test_toolbox_always_answers_with_valid_json(data, name, arguments):
    toolbox = Toolbox(data, MemoryJournal(), "s1", lambda: NOW)
    output, is_error = toolbox.run(name, arguments)
    assert isinstance(is_error, bool)
    json.loads(output, parse_constant=_reject_constant)


def _reject_constant(constant):
    raise AssertionError(f"not strict JSON: {constant}")


PHONE_FORMATS = (
    "{ddd}{n}",
    "({ddd}) {n5}-{n4}",
    "{ddd} {n5} {n4}",
    "+55 {ddd} {n5}-{n4}",
    "+55({ddd}){n}",
    "0{ddd} {n5} {n4}",
    "{n5}-{n4}",
)


@example(number="910000000", ddd="11", shape="{ddd}{n}", before="A", after="")
@given(
    number=st.integers(10**8, 10**9 - 1).map(lambda n: f"9{n:09d}"[:9]),
    ddd=st.integers(11, 99).map(str),
    shape=st.sampled_from(PHONE_FORMATS),
    before=st.text(max_size=12),
    after=st.text(max_size=12),
)
def test_mask_contact_never_leaves_a_phone_whole(number, ddd, shape, before, after):
    phone = shape.format(ddd=ddd, n=number, n5=number[:5], n4=number[5:])
    masked = mask_contact(f"{before}{phone}{after}")
    assert phone not in masked
    assert number not in masked.replace(" ", "").replace("-", "")


def _expected_open(moment: datetime) -> bool:
    good_fridays = {date(2026, 4, 3), date(2027, 3, 26), date(2028, 4, 14)}
    fixed = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}
    if moment.date() in good_fridays or (moment.month, moment.day) in fixed:
        return False
    weekday, hour = moment.weekday(), moment.hour + moment.minute / 60
    if weekday < 5:
        return 9 <= hour < 18
    return weekday == 5 and 9 <= hour < 13


@given(moment=st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2028, 12, 31, 23, 59)))
def test_describe_never_fails_and_says_open_only_inside_hours(moment):
    text = describe(moment)
    assert ("está aberta" in text) == _expected_open(moment)
