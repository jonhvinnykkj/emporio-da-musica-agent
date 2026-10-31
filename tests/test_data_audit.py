from emporio.data_audit import find_inconsistencies


def test_audit_reports_the_known_traps(catalog, book):
    report = "\n".join(find_inconsistencies(catalog, book))
    for fragment in ("136", "130", "pedido 3", "pedido 20", "categoria"):
        assert fragment in report


def test_audit_reports_installments_pix_and_shared_email(catalog, book):
    report = "\n".join(find_inconsistencies(catalog, book))
    assert "pedido 18" in report and "PIX" in report and "bruno.martins@jmail.com" in report


def test_audit_returns_one_line_per_finding(catalog, book):
    assert all("\n" not in line for line in find_inconsistencies(catalog, book))
