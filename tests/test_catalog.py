import pytest

from emporio.catalog import (
    COMING_SOON,
    DISCONTINUED,
    OUT_OF_STOCK,
    Catalog,
    DataError,
    description_contradicts_name,
)


def names(result):
    return {product["nome"] for product in result["produtos"]}


def test_acoustic_guitars_up_to_1000_exclude_unavailable_items(catalog):
    result = catalog.search(category="Violões", max_price=1000, limit=50)
    assert result["total_encontrado"] == 12
    assert "Giannini GF-3D Dreadnought Sunburst" not in names(result)  # stock 0
    assert "Shelby SN-7C 7 Cordas Nylon Natural" not in names(result)  # discontinued


def test_price_filter_uses_promotional_price(catalog):
    result = catalog.search(category="Ukuleles", max_price=450, min_price=430)
    assert "Ohana CK-20 Concert Natural" in names(result)  # R$ 549 with 20% off


def test_finds_model_written_with_a_hyphen(catalog):
    result = catalog.search(query="takamine gd-20")
    assert result["correspondencia"] == "exata"
    assert names(result) == {"Takamine GD20 Dreadnought Natural"}


def test_tolerates_typos(catalog):
    assert "Takamine GD20 Dreadnought Natural" in names(catalog.search(query="takamini gd20"))


def test_category_word_in_query_becomes_a_filter(catalog):
    result = catalog.search(query="violão yamaha", limit=50)
    assert names(result) and all("Yamaha" in name for name in names(result))
    assert all(product["categoria"] == "Violões" for product in result["produtos"])


def test_model_we_do_not_sell_is_only_a_partial_match(catalog):
    result = catalog.search(query="takamine gd30")
    assert result["correspondencia"] == "parcial"


def test_out_of_stock_item_comes_with_alternatives(catalog):
    result = catalog.search(query="giannini gf-3d")
    assert result["produtos"] == []
    assert result["indisponiveis"][0]["disponibilidade"] == OUT_OF_STOCK
    assert all(item["disponibilidade"] == "disponivel" for item in result["alternativas"])


def test_status_wins_over_stock(catalog):
    assert catalog.products[136].stock == 13 and catalog.products[136].availability == DISCONTINUED
    assert catalog.products[130].stock == 2 and catalog.products[130].availability == COMING_SOON


def test_unavailable_items_never_expose_a_price(catalog):
    item = catalog.search(query="ibanez bass 2x")["indisponiveis"][0]
    assert "preco" not in item and "preco_no_pix" not in item


def test_empty_categories_are_reported(catalog):
    result = catalog.search(query="saxofone")
    assert result["categoria_sem_produtos"] is True
    assert result["produtos"] == []


def test_description_from_another_brand_is_hidden_and_not_searched(catalog):
    assert description_contradicts_name(
        "Music Man Bass 1X Electric Bass", "Contrabaixo elétrico Fender Jazz Bass"
    )
    assert not catalog.products[135].description_reliable
    data = catalog.products[135].to_dict()
    assert "descricao" not in data and "especificacoes" not in data
    assert catalog.search(query="fender", category="Baixos")["produtos"] == []


def test_consistent_descriptions_stay(catalog):
    assert catalog.products[95].description_reliable
    assert catalog.products[141].description_reliable


def test_overview_flags_categories_without_items(catalog):
    overview = catalog.overview()
    assert "Cordas Orquestrais: nenhum item" in overview
    assert "Violões: 33 modelos" in overview


def test_list_shows_five_and_reports_the_total(catalog):
    result = catalog.search(category="Violões", max_price=1000)
    assert (result["total_encontrado"], result["mostrando"]) == (12, 5)
    assert len(result["produtos"]) == 5


def test_on_sale_lists_the_four_active_promotions(catalog):
    result = catalog.search(on_sale=True, limit=50)
    assert {item["id"] for item in result["produtos"]} == {90, 94, 121, 127}
    assert all(item["promocao_ativa"] for item in result["produtos"])


def test_every_item_says_if_a_promotion_is_active(catalog):
    item = catalog.search(query="takamine gd20")["produtos"][0]
    assert item["promocao_ativa"] is False


def test_flagged_product_hides_description_and_specs(catalog):
    data = catalog.products[135].to_dict()
    assert "descricao" not in data and "especificacoes" not in data
    assert "nota_interna" in data


def test_inverted_price_range_is_empty(catalog):
    assert catalog.search(min_price=1000, max_price=500)["total_encontrado"] == 0


def test_nonsense_query_finds_nothing(catalog):
    assert catalog.search(query="xyzzy")["correspondencia"] == "nenhuma"


def test_missing_file_names_the_file(tmp_path):
    with pytest.raises(DataError, match="categories.csv"):
        Catalog(tmp_path)


def test_missing_column_names_file_and_column(tmp_path, data_dir):
    for source in data_dir.glob("*.csv"):
        (tmp_path / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "categories.csv").write_text("category_id,title\n1,Guitarras\n", encoding="utf-8")
    with pytest.raises(DataError, match="categories.csv.*name"):
        Catalog(tmp_path)


def test_invalid_value_names_the_file(tmp_path, data_dir):
    for source in data_dir.glob("*.csv"):
        (tmp_path / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "categories.csv").write_text("category_id,name\nabc,Guitarras\n", encoding="utf-8")
    with pytest.raises(DataError, match="categories.csv"):
        Catalog(tmp_path)
