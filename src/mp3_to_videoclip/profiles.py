"""Versioned defaults copied into NEW productions, never injected into old ones."""

from decimal import Decimal

from . import styles

DEFAULT_MODEL = "google-nano-banana-2-1"
DEFAULT_MODEL_AIR = "google:nano-banana@2.1"
LEGACY_MODEL = "bfl-flux-2-klein-4b"
LEGACY_STYLE_PRESET_ID = "photoreal-painted-v1"
STYLE_PRESET_ID = "photographic-painted-v2"
DEFAULT_MAX_CORRECTIONS = 1

# The approved core is file-backed so it is one selectable preset, not a rule for
# every production. The verbatim text and its hash are unchanged.
DEFAULT_STYLE = styles.preset(STYLE_PRESET_ID).look

# Exact user control, including its scene/optics/lettering; never prefixed globally.
ROOFTOP_CONTROL_PROMPT = """A fully painted comic cover panel driven toward photorealism: a realistic
depiction in the painted tradition of Alex Ross and Gabriele Dell'Otto, weighted
roughly 70% Ross for photographic anatomy, skin and lighting, 30% Dell'Otto for
crushed blacks, hard specular highlights and gritty texture.

A lone adult man in a soaked charcoal overcoat stands on a wet rooftop at night,
seen from a low heroic angle, chin lifted, rain streaking past him in diagonal
silver lines. Behind him the city drops into a deep canyon of brick and steel,
one warm sodium streetlight and one cold searchlight beam converging on his
shoulders.

Rendered at photographic fidelity with a brush: skin with visible pores, stubble
and subsurface scattering, individual wet hairs, rain beading on the fabric,
visible wool and canvas weave, leather scuffed and creased, accurate near-to-far
perspective and volume. Shot on a 50mm lens at f/2.0, the figure tack sharp while
the city falls into soft focus behind him, veiling glare and a faint lens flare
where the searchlight crosses the frame, controlled blown highlights on the wet
coat, fine 35mm film grain, natural colour science, believable exposure.

From the Dell'Otto side, translated into photographic terms: ink-black shadow
shapes with detail crushed out, brilliant specular whites, hard rim light, gritty
high-contrast punch, and the faintest trace of halftone print grain in the
shadows.

Hyper-detailed photorealism rendered entirely by brush — a painting that could be
mistaken for a photograph. Not a 3D render, not CGI, not a cel-shaded or
outlined cartoon, not waxy plastic skin.

Headline text: the exact words "THE LAST LIGHT" in heavy condensed capitals with
a slight upward arc, across the upper third of the frame, dark ink with a thin
warm rim light and a hard ink shadow beneath. A small caption box in the
lower-left corner reads exactly "The city never sleeps." in modest regular
capitals. All lettering clean, typeset, correctly spelled and fully readable, set
like sharp offset print. No other text, numbers, logos, symbols or watermarks
anywhere in the frame.

Wide 16:9 composition, cinematic scale, 1376x768."""
DEFAULT_IMAGE_RULES = styles.preset(STYLE_PRESET_ID).image_rules


def default_settings() -> dict:
    return {"thinkingLevel": "minimal", "imageSearch": False, "webSearch": False}


# The user explicitly judged these exact pixels, not every future scene. Retain
# the private original locally for visual comparison; this does NOT authorize an
# upload or make its man/rooftop/weather/lettering part of the reusable style.
STYLE_BENCHMARK = {
    "preset": STYLE_PRESET_ID,
    "status": "user-approved",
    "approval_note": "the style is perfect. solidify this so when generating total difference story board stils, we get this fantastic style",
    "image": "style-tests/the-last-light-control-v001/assets/rooftop-control/v001-2edbbe00-18a2-4776-9aca-67d863f5ea36.jpg",
    "image_sha256": "acab948b7bbee1898bd2ad3d6cf02a43654b976c5953028cf86f10cd192addad",
    "task_uuid": "2edbbe00-18a2-4776-9aca-67d863f5ea36",
    "prompt_hash": "906f30a424fc4db87d9d7b5d0d9913044d171324d4ccf6a111304200b03d0ef2",
    "style_core_hash": "70e8d61b3a755e865c6b3e4f313d8be1289c4f69101376cae3a4b1fe4276e4b6",
    "settings_hash": "7a486784565b60c80591d82fa7291b1a3d0e7fab1b370b4994d39088f67fd2d8",
    "scope": "Rendering style only; new scene fidelity still requires inspected proofs.",
    "reference_upload_authorized": False,
}


def default_size(aspect: str) -> list[int]:
    return [1376, 768] if aspect == "16:9" else [768, 1376]


# Shared text/audio provider defaults (music listening and lyric transcription).
DEFAULT_TEXT_MODEL = "google-gemini-3-1-flash-lite"
DEFAULT_RESERVATION = "0.05"
UPLOAD_RESERVATION = Decimal("0.01")
