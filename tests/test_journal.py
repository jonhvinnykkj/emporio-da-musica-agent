import json
import threading

from emporio.journal import Journal, mask_contact


def test_mask_hides_phone_and_email_inside_a_sentence():
    masked = mask_contact("sou a Ana, (67) 99654-7821 e ana@coldmail.com")
    assert "99654" not in masked and "coldmail" not in masked and "7821" in masked


def test_mask_keeps_prices_and_order_numbers():
    text = "pedido 8, R$ 1.199,80 em 3x"
    assert mask_contact(text) == text


def test_mask_handles_international_format():
    masked = mask_contact("+55 67 99654-7821")
    assert "99654" not in masked and masked.endswith("7821")


def test_record_writes_one_masked_json_line_per_event(tmp_path):
    path = tmp_path / "logs" / "journal.jsonl"
    journal = Journal(path)
    journal.record("mensagem", "s1", {"texto": "meu e-mail é ana@coldmail.com", "n": 8})
    journal.record("mensagem", "s1", {"itens": ["(67) 99654-7821"]})
    lines = path.read_text(encoding="utf-8").splitlines()
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first["kind"] == "mensagem" and first["session_id"] == "s1" and first["ts"].endswith("+00:00")
    assert "coldmail" not in lines[0] and first["payload"]["n"] == 8
    assert "99654" not in lines[1] and second["payload"]["itens"][0].endswith("7821")


def test_journal_without_path_does_nothing():
    Journal(None).record("mensagem", "s1", {"texto": "oi"})


def test_journal_write_failure_does_not_raise(tmp_path):
    Journal(tmp_path).record("mensagem", "s1", {"texto": "oi"})  # path is a directory


def test_concurrent_records_do_not_interleave(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = Journal(path)
    threads = [
        threading.Thread(target=journal.record, args=("m", f"s{i}", {"texto": "x" * 500})) for i in range(20)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]) == 20


def test_mask_hides_a_phone_glued_to_a_word():
    masked = mask_contact("whatsapp67996547821 ou fone:6733414444")
    assert "99654" not in masked and "3341" not in masked
