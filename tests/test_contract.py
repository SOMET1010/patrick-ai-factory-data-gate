from datagate.contract import load_contract


def test_load_valid_contract() -> None:
    contract = load_contract("contracts/hermes-review.yaml")

    assert contract["version"] == 1
    assert contract["database"] == "hermes-review"
    assert contract["schema"] == "public"
    assert contract["structure"] == []
    assert contract["audit"] == []
