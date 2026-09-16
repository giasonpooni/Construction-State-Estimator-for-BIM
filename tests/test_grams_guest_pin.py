import pytest

pytest.importorskip("sensitivity")
from sensitivity.grams_guest import receipt


def test_gat_reads_jspt_grams_receipt():
    body = receipt()
    assert body["verdict"] == "PASS"
    assert body["profile"] == "grams-micro-v1"
    assert body["P_prime"][0][0] == 1_000_000.0
