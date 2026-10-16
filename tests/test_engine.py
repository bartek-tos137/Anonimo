import pytest

from anonimo.config import Policy, Rule
from anonimo.engine import Blocked, Engine, valid_pesel, valid_nip, valid_polish_iban


def test_invoice_preserves_task_and_amount(engine):
    invoice = (
        "Sprawdź VAT na tej fakturze.\nSprzedawca: Testowa Firma Sp. z o.o.\n"
        "Adres: ul. Przykładowa 7, Warszawa\nNIP: 5260250274\n"
        "Konto: PL61 1090 1014 0000 0712 1981 2874\n"
        "Kontakt: faktury@example.test\nNetto: 1000 PLN; VAT: 23%; brutto: 1230 PLN"
    )
    [clean], counts = engine.sanitize([invoice])
    for value in ["Testowa Firma", "Przykładowa", "5260250274", "1090", "faktury@example.test"]:
        assert value not in clean
    assert "Sprawdź VAT" in clean and "1000 PLN" in clean and "1230 PLN" in clean
    assert set(counts) >= {"INVOICE_PARTY", "ADDRESS", "TAX_ID", "BANK_ACCOUNT", "EMAIL"}


def test_repeat_mapping_is_per_request_and_avoids_existing_placeholders(engine):
    clean, _ = engine.sanitize(["[EMAIL_1] ala@example.test", "ala@example.test bob@example.test"])
    assert clean == ["[EMAIL_1] [EMAIL_2]", "[EMAIL_2] [EMAIL_3]"]
    assert engine.sanitize(["bob@example.test"])[0] == ["[EMAIL_1]"]


def test_partial_overlap_removes_the_entire_sensitive_region():
    engine = Engine(Policy(rules=[Rule(id="whole", label="CODE", literal="abcdef", priority=1),
                                 Rule(id="part", label="SECRET", literal="cde", priority=2)]))
    assert engine.sanitize(["XabcdefY"])[0] == ["X[SECRET_1]Y"]


def test_secret_inside_code_block_does_not_leak_source(engine):
    text = "Explain ```python\npassword=companysecret\nprint('internal algorithm')\n``` please"
    [clean], _ = engine.sanitize([text])
    assert "companysecret" not in clean and "internal algorithm" not in clean
    assert clean.startswith("Explain [") and clean.endswith(" please")


def test_custom_rule_block_wins():
    engine = Engine(Policy(rules=[Rule(id="block", label="CONFIDENTIAL", literal="Project Falcon", action="block")]))
    with pytest.raises(Blocked, match="policy_block"):
        engine.sanitize(["Tell me about Project Falcon"])


def test_regex_timeout_fails_closed():
    engine = Engine(Policy(regex_timeout_seconds=0.001, rules=[Rule(id="slow", label="TEST", pattern="(a+)+$")]))
    with pytest.raises(Blocked, match="rule_timeout"):
        engine.sanitize(["a" * 10000 + "!"])


def test_length_limit_blocks(engine):
    with pytest.raises(Blocked, match="text_limit_exceeded"):
        engine.sanitize(["x" * 50001])


def test_checksum_validation():
    assert valid_pesel("44051401458")
    assert not valid_pesel("44051401459")
    assert not valid_pesel("00000000000")
    assert valid_nip("526-025-02-74")
    assert not valid_nip("5260250275")
    assert not valid_nip("0000000000")
    assert valid_polish_iban("PL61 1090 1014 0000 0712 1981 2874")
    assert not valid_polish_iban("PL62 1090 1014 0000 0712 1981 2874")


def test_custom_literal_unicode_casefold():
    engine = Engine(Policy(rules=[Rule(id="project", label="PROJECT", literal="Żółty Projekt", case_sensitive=False)]))
    assert engine.sanitize(["To ŻÓŁTY PROJEKT."])[0] == ["To [PROJECT_1]."]


def test_no_detection_is_not_a_safety_guarantee(engine):
    # Ordinary unlabelled names require contextual detection; regex-only mode has this gap.
    assert engine.sanitize(["Anna Kowalska"])[0] == ["Anna Kowalska"]


def test_excessive_findings_are_bounded():
    engine = Engine(Policy(rules=[Rule(id="many", label="TEST", pattern=".")]))
    with pytest.raises(Blocked, match="finding_limit_exceeded"):
        engine.sanitize(["a" * 5000])
