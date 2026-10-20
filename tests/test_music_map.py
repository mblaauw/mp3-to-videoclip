from test_music_listening import Client
from test_music_listening import project as project  # re-export the pytest fixture

from mp3_to_videoclip import generation as G
from mp3_to_videoclip import music_analysis as M
from mp3_to_videoclip.music_map import build_music_map, write_music_map
from mp3_to_videoclip.storage import read_json, write_json


def test_music_map_keeps_measurements_and_interpretation_separate(project):
    local = read_json(project / "work/music.json")
    local["fine_windows"] = [
        {
            "time": n / 2,
            "end": (n + 1) / 2,
            "rms_db": -15,
            "level_db": -3,
            "low_bass_share": 0.6,
            "high_share": 0.1,
            "spectral_centroid_hz": 900,
            "onset_density_per_s": 5,
        }
        for n in range(8)
    ]
    local["candidate_changes"] = [{"time": 2.5, "reviewed": False}]
    write_json(project / "work/music.json", local)
    fake = Client(project)
    quote = M.quote_music(project, client=fake)
    G.authorize(project, quote["id"], "0.05", "test user authorized audio analysis")
    M.run_music(project, quote["id"], fake)
    result = write_music_map(project)
    assert result["approved"] is False and result["passages"] == 3
    mapped = build_music_map(project)
    assert mapped["passages"][0]["measured"]["low_bass_share_window_mean"] == 0.6
    assert mapped["passages"][0]["interpretation"]["confidence"] == "low"
    assert not (project / "work/events.json").exists()
    assert all(
        e["timing_basis"] == "estimated" and e["source"] == "audio-model"
        for e in mapped["draft_event_map"]["events"]
    )
    edited = read_json(project / M.LISTENING_PATH)
    edited["draft"]["passages"][0]["label"] = "User corrected interpretation"
    write_json(project / M.LISTENING_PATH, edited)
    write_music_map(project)
    assert len(list((project / "work/music-map-history").glob("*.json"))) == 1
