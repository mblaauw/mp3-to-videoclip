"""What a final may be asked for, and what real FFmpeg does with the sound."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_story_film import tone

from mp3_to_videoclip import audio as sound
from mp3_to_videoclip import remotion
from mp3_to_videoclip.services import render as service


def _project(kind=None, spine=None):
    return SimpleNamespace(kind=kind, spine=spine)


def test_the_default_final_asks_for_nothing_new():
    choices = service.final_options(_project(), None)
    assert choices == {"final_capture": "png"}
    assert service._render_arguments(choices) == {}
    assert remotion._delivery_audio(Path("x"), None) == ([], None)


@pytest.mark.parametrize("kind", ["promo", "advert"])
def test_a_promo_or_advert_may_be_normalised(kind):
    choices = service.final_options(_project(kind), {"loudness": True})
    assert choices["audio_delivery"]["loudness"] == {"target_lufs": -14.0, "true_peak": -1.0}


@pytest.mark.parametrize(
    ("project", "words"),
    [(_project("music_video"), "master is the mix"), (_project(None), "master is the mix"),
     (_project("narrative", "soundtrack"), "own loudness")],
)  # fmt: skip
def test_other_kinds_refuse_with_their_reason(project, words):
    with pytest.raises(ValueError, match=words):
        service.final_options(project, {"loudness": True})
    assert words in service.loudness_refusal(project)


def test_capture_and_rate_are_only_what_is_on_offer():
    choices = service.final_options(_project(), {"capture": "jpeg90", "sample_rate": 48000})
    assert choices["capture"] == {"format": "jpeg", "quality": 90}
    assert choices["audio_delivery"] == {"sample_rate": 48000}
    for bad in ({"capture": "webp"}, {"sample_rate": 44100}, {"nonsense": 1}):
        with pytest.raises(ValueError):
            service.final_options(_project(), bad)


def _probe(path):
    out = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate", "-of", "json", str(path)],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    return int(json.loads(out)["streams"][0]["sample_rate"])


def test_two_passes_land_within_one_lu_of_the_target_at_48k(tmp_path):
    source = tone(tmp_path / "a.wav", 12.0, amplitude=0.05)
    arguments, record = remotion._delivery_audio(source, {"loudness": service.LOUDNESS})
    target = tmp_path / "out.m4a"
    subprocess.run(
        [shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-i", str(source),
         "-c:a", "aac", "-b:a", "192k", *arguments, str(target)],
        check=True,
    )  # fmt: skip
    remotion._record_output_loudness(target, record)
    assert record["sample_rate"] == 48000
    assert _probe(target) == 48000
    assert abs(record["loudness"]["output_i"] - (-14.0)) <= 1.0
    assert record["loudness"]["input_i"] < -20
    assert record["loudness"]["output_tp"] <= -0.5


def test_silence_has_no_loudness_to_set(tmp_path):
    source = tone(tmp_path / "s.wav", 3.0, amplitude=0.0)
    assert sound.loudness_stats(source) is None
    with pytest.raises(ValueError, match="silent"):
        remotion._delivery_audio(source, {"loudness": service.LOUDNESS})
