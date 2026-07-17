from src.lingua_viva.publication import PublicationService


def test_publication_status_returns_claims():
    status = PublicationService().get_status()

    assert status["claim_count"] >= 1
    assert status["safe_to_claim"]
    assert "release_checklist" in status


def test_publication_status_flags_unsafe_claims():
    status = PublicationService().get_status()

    blocked_ids = {claim["id"] for claim in status["blocked"]}
    assert "lv-claim-global-uniqueness" in blocked_ids
    assert status["not_publication_ready"] is True
