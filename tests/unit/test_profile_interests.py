import pytest
from pydantic import ValidationError

from app.domain.interests import normalize_interests
from app.schemas.models import UserInterestsUpdate


def test_normalization_deduplicates_unicode_case_and_spaces_but_keeps_accents() -> None:
    assert normalize_interests([" ＰＹＴＨＯＮ ", "Python", "  música  en  vivo ", "Straße"]) == (
        "python",
        "música en vivo",
        "strasse",
    )
    assert normalize_interests(["música", "musica"]) == ("música", "musica")
    assert normalize_interests([]) == ()


@pytest.mark.parametrize("values", [[""], ["   "], ["a" * 41], [str(i) for i in range(21)]])
def test_invalid_interests_are_rejected(values: list[str]) -> None:
    with pytest.raises(ValidationError):
        UserInterestsUpdate(interests=values)


def test_interests_update_cannot_choose_another_account() -> None:
    with pytest.raises(ValidationError):
        UserInterestsUpdate.model_validate({"interests": ["python"], "user_id": "another"})
