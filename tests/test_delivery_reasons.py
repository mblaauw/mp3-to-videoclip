"""The Film checklist turns engine approval prose into owner-facing sentences."""

from mp3_to_videoclip.domain.delivery import _human_reason


def test_plural_subjects_take_plural_verbs():
    assert _human_reason("graphics needs current user approval", "graphics") == (
        "The titles need your approval."
    )
    assert _human_reason("lyrics needs current user approval", "brief") == (
        "The lyrics need your approval."
    )
    assert _human_reason("brief needs current user approval", "storyboard") == (
        "The story needs your approval."
    )
    assert _human_reason("graphics is missing; its artifact has not been created", "graphics") == (
        "The titles have not been made yet."
    )
    assert _human_reason("storyboard is missing; its artifact has not been created", "proof") == (
        "The storyboard has not been made yet."
    )
