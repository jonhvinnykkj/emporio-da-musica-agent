from emporio.catalog import COMING_SOON, DISCONTINUED, OUT_OF_STOCK, description_contradicts_name


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
    assert description_contradicts_name("Music Man Bass 1X Electric Bass", "Contrabaixo elétrico Fender Jazz Bass")
    assert not catalog.products[135].description_reliable
    assert "descricao" not in catalog.products[135].to_dict()
    assert catalog.search(query="fender", category="Baixos")["produtos"] == []


def test_consistent_descriptions_stay(catalog):
    assert catalog.products[95].description_reliable
    assert catalog.products[141].description_reliable


def test_active_promotions(catalog):
    report = catalog.promotions_report()
    assert {item["id"] for item in report["promocoes_ativas"]} == {90, 94, 121, 127}


def test_expired_campaign_is_reported(catalog):
    report = catalog.promotions_report("black friday")
    assert report["promocoes_ativas"] == []
    assert report["campanhas_encerradas"] == ["Black Friday"]


def test_overview_flags_categories_without_items(catalog):
    overview = catalog.overview()
    assert "Cordas Orquestrais: nenhum item" in overview
    assert "Violões: 33 modelos" in overview
