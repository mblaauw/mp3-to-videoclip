"""Vocal isolation and word recognition, run inside the private tools environment.

This file is launched by `lyric_tools.py` with that environment's Python, so it
imports nothing from this project. It reports one JSON object per line on stdout.
"""

import json
import sys
import tempfile
from pathlib import Path

DEMUCS_MODEL = "htdemucs"
PARAKEET_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
# Chunking keeps a four-minute song within memory on a 16 GB machine.
CHUNK_SECONDS = 120
OVERLAP_SECONDS = 15


def say(step: str) -> None:
    print(json.dumps({"step": step}), flush=True)


def prepare() -> None:
    """Fetch both models now, so a song's first run needs no download."""
    say("downloading-vocal-model")
    from demucs.pretrained import get_model

    get_model(DEMUCS_MODEL)
    say("downloading-word-model")
    from parakeet_mlx import from_pretrained

    from_pretrained(PARAKEET_MODEL)


def hear(audio: str, out: str) -> None:
    say("isolating-vocals")
    from demucs.separate import main as separate

    with tempfile.TemporaryDirectory() as folder:
        separate(["-n", DEMUCS_MODEL, "--two-stems=vocals", "-d", "cpu", "-o", folder, audio])
        vocals = next(Path(folder).glob(f"{DEMUCS_MODEL}/*/vocals.wav"))
        say("hearing-words")
        from parakeet_mlx import from_pretrained

        model = from_pretrained(PARAKEET_MODEL)
        result = model.transcribe(
            str(vocals), chunk_duration=CHUNK_SECONDS, overlap_duration=OVERLAP_SECONDS
        )
    tokens = [
        {"text": token.text, "start": float(token.start), "end": float(token.end)}
        for sentence in result.sentences
        for token in sentence.tokens
    ]
    Path(out).write_text(json.dumps({"tokens": tokens}, ensure_ascii=False))
    say("done")


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    else:
        hear(sys.argv[2], sys.argv[3])
