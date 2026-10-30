"""Your own idea stays yours: sorting may move your words, never change them."""

from __future__ import annotations

import asyncio
import json

import pytest
from api_support import api_client, make_api_project

from mp3_to_videoclip import idea, story_beats
from mp3_to_videoclip import production as P
from mp3_to_videoclip.director import prompts, tools
from mp3_to_videoclip.storage import read_json

PASTE = """Two strangers meet in a dream garden.

They walk until the light fails. Soft, hazy, photographic. No lip-sync.

Nobody looks at the lens. "It's over," she says - and the garden closes."""

SORTED = {
    "story": [
        "Two strangers meet in a dream garden.",
        "They walk until the light fails.",
        '"It’s over," she says — and the garden closes.',
    ],
    "style": ["Soft, hazy, photographic."],
    "rules": ["Nobody looks at the lens."],
    "avoid": ["No lip-sync."],
}


@pytest.fixture
def root(tmp_path):
    return make_api_project(tmp_path)


def test_a_paste_is_kept_whole_as_the_story_before_any_sorting(root):
    style = P.load_brief(root).style
    kept = idea.keep_paste(root, f"\n{PASTE}\n")
    brief = P.load_brief(root)
    assert brief.treatment == PASTE
    assert brief.style == style
    assert kept["text"] == PASTE and kept["sorted"] is None and kept["current"] is True
    assert read_json(
        root
        / "work/brief-history"
        / next(path.name for path in (root / "work/brief-history").iterdir())
    )


def test_sorting_writes_the_pastes_own_characters_not_the_writers_copy(root):
    idea.keep_paste(root, PASTE)
    saved = idea.apply_sort(root, SORTED, by="writer")
    brief = P.load_brief(root)
    assert brief.treatment == (
        "Two strangers meet in a dream garden.\n\n"
        "They walk until the light fails.\n\n"
        '"It\'s over," she says - and the garden closes.'
    )
    assert brief.style == "Soft, hazy, photographic."
    assert brief.direction == "Nobody looks at the lens."
    assert "No lip-sync." in brief.avoid
    assert saved["sorted_by"] == "writer" and saved["current"] is True


def test_sentences_of_one_paragraph_stay_one_paragraph(root):
    idea.keep_paste(root, "One walks. Two runs. Soft light.")
    idea.apply_sort(
        root, {"story": ["One walks.", "Two runs."], "style": ["Soft light."]}, by="writer"
    )
    assert P.load_brief(root).treatment == "One walks. Two runs."


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"story": ["Two strangers meet in a beautiful garden."]}, "not word for word"),
        ({"style": ["Soft, hazy, photographic.", "Soft, hazy, photographic."]}, "used twice"),
        ({"rules": []}, "not assigned"),
        ({"genre": ["x"]}, "unknown parts"),
        ({"style": [""]}, "empty entry"),
    ],
)
def test_changed_doubled_or_dropped_words_are_refused_and_nothing_is_saved(root, change, message):
    idea.keep_paste(root, PASTE)
    with pytest.raises(ValueError, match=message):
        idea.apply_sort(root, {**SORTED, **change}, by="writer")
    assert P.load_brief(root).treatment == PASTE
    assert idea.latest(root)["sorted"] is None


def test_a_paste_with_no_story_leaves_the_story_empty(root):
    idea.keep_paste(root, "Soft light. No faces.")
    idea.apply_sort(root, {"style": ["Soft light."], "avoid": ["No faces."]}, by="writer")
    assert P.load_brief(root).treatment == ""


def test_moving_a_sentence_recomposes_the_brief_from_what_was_there_before(root):
    before = P.load_brief(root)
    idea.keep_paste(root, PASTE)
    idea.apply_sort(root, SORTED, by="writer")
    moved = idea.apply_sort(
        root,
        {
            **SORTED,
            "style": [],
            "rules": ["Nobody looks at the lens.", "Soft, hazy, photographic."],
        },
        by="owner",
    )
    brief = P.load_brief(root)
    assert brief.style == before.style
    assert brief.direction == "Soft, hazy, photographic. Nobody looks at the lens."
    assert moved["sorted_by"] == "owner"


def test_sorting_refuses_to_overwrite_edits_made_since(root):
    idea.keep_paste(root, PASTE)
    idea.apply_sort(root, SORTED, by="writer")
    P.update_brief(root, {"treatment": "My rewritten story."})
    assert idea.latest(root)["current"] is False
    with pytest.raises(ValueError, match="overwrite those edits"):
        idea.apply_sort(root, SORTED, by="owner")
    assert P.load_brief(root).treatment == "My rewritten story."


def test_the_log_only_ever_grows(root):
    idea.keep_paste(root, PASTE)
    first = (root / idea.LOG).read_text()
    idea.apply_sort(root, SORTED, by="writer")
    idea.keep_paste(root, "A second idea.")
    log = (root / idea.LOG).read_text()
    assert log.startswith(first)
    assert [json.loads(line)["kind"] for line in log.splitlines()] == ["paste", "sort", "paste"]
    assert idea.latest(root)["text"] == "A second idea."


def test_starting_over_on_your_last_sort_restores_the_base_it_was_sorted_from(root):
    before = P.load_brief(root)
    idea.keep_paste(root, PASTE)
    idea.apply_sort(root, SORTED, by="writer")
    idea.keep_paste(root, "A second idea.")
    brief = P.load_brief(root)
    assert brief.style == before.style and brief.direction == before.direction
    assert brief.avoid == before.avoid


def test_tools_reach_the_writer_and_the_refusal_comes_back_as_an_error(tmp_path):
    root = make_api_project(tmp_path)
    idea.keep_paste(root, PASTE)

    def call(name, **arguments):
        result = asyncio.run(
            tools.dispatch(name, {"slug": "production", **arguments}, projects_dir=tmp_path)
        )
        return json.loads(result)

    assert call("get_idea")["text"] == PASTE
    assert "error" in call("sort_idea", **{**SORTED, "story": ["Not your words."]})
    assert call("sort_idea", **SORTED)["sorted"]["style"] == SORTED["style"]


def test_writer_has_the_import_and_place_tasks_and_a_button_can_name_them(tmp_path):
    root = make_api_project(tmp_path)
    assert prompts.assemble(root, "story", role="writer", task="import").meta["task"] == "import"
    assert prompts.assemble(root, "story", role="writer", task="place").meta["task"] == "place"
    client = api_client(tmp_path)
    response = client.post(
        "/api/projects/production/chat",
        json={"message": "go", "stage": "story", "role": "writer", "task": "made_up"},
    )
    assert response.status_code == 400


def test_idea_routes_keep_and_move_and_explain_a_refusal(tmp_path):
    make_api_project(tmp_path)
    client = api_client(tmp_path)
    url = "/api/projects/production/idea"
    assert client.get(url).json() == {"idea": None}
    assert client.post(url, json={"text": "  "}).status_code == 400
    assert client.post(url, json={"text": PASTE}).json()["idea"]["text"] == PASTE
    assert client.get(url).json()["idea"]["sorted"] is None
    refused = client.put(f"{url}/sorted", json={**SORTED, "story": ["Not yours."]})
    assert refused.status_code == 400 and "word for word" in refused.json()["detail"]
    assert client.put(f"{url}/sorted", json=SORTED).json()["idea"]["sorted_by"] == "owner"


# ---- the story on the song ----


STORY = "One walks.\n\nTwo runs.\n\nThree stops."


def _placed(*spans):
    return {"passages": [{"start": a, "end": b, "text": text} for a, b, text in spans]}


def test_placing_keeps_words_in_the_treatment_and_does_not_change_the_brief(root):
    P.update_brief(root, {"treatment": STORY})
    brief = read_json(root / "brief.json")
    story_beats.place_story(root, _placed((0, 1, "One walks."), (1, 2, "Two runs. Three stops.")))
    assert read_json(root / "brief.json") == brief
    assert [(item["start"], item["text"]) for item in story_beats.passages(root)] == [
        (0, "One walks."),
        (1, "Two runs.\n\nThree stops."),
    ]


@pytest.mark.parametrize(
    ("spans", "message"),
    [
        (((0, 2, "One walks."), (2, 4, "Two ran. Three stops.")), "unchanged and in order"),
        (((0, 2, "One walks."),), "unchanged and in order"),
        (((0, 2, "Two runs."), (2, 4, "One walks. Three stops.")), "unchanged and in order"),
        (((0, 3, "One walks."), (2, 4, "Two runs. Three stops.")), "without overlapping"),
        (((0, 2, "One walks."), (2, 99999, "Two runs. Three stops.")), "the film is"),
    ],
)
def test_placement_refuses_changed_words_and_impossible_times(root, spans, message):
    P.update_brief(root, {"treatment": STORY})
    with pytest.raises(ValueError, match=message):
        story_beats.place_story(root, _placed(*spans))
    assert not (root / story_beats.PATH).exists()


def test_an_edited_passage_loses_its_time_and_the_others_keep_theirs(root):
    P.update_brief(root, {"treatment": STORY})
    story_beats.place_story(
        root, _placed((0, 0.5, "One walks."), (0.5, 1, "Two runs."), (1, 2, "Three stops."))
    )
    P.update_brief(root, {"treatment": "One walks.\n\nTwo flies.\n\nThree stops."})
    assert [(item["text"], item["start"]) for item in story_beats.passages(root)] == [
        ("One walks.", 0),
        ("Two flies.", None),
        ("Three stops.", 1),
    ]


def test_a_story_with_no_placement_reads_by_paragraph_with_offsets(root):
    P.update_brief(root, {"treatment": STORY})
    items = story_beats.passages(root)
    assert [item["text"] for item in items] == ["One walks.", "Two runs.", "Three stops."]
    assert all(item["start"] is None for item in items)
    assert [STORY[item["from"] : item["to"]] for item in items] == [item["text"] for item in items]
