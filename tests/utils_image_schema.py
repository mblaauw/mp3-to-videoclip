"""A small stand-in for a live image model's schema, and a picture to answer with."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def image_schema(*, negative=False, references=True, air="google:nano-banana@2.1"):
    properties = {
        "taskType": {"const": "imageInference"},
        "taskUUID": {"type": "string"},
        "model": {"const": air},
        "positivePrompt": {"type": "string"},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "numberResults": {"type": "integer"},
        "outputType": {"enum": ["URL"]},
        "outputFormat": {"enum": ["JPG"]},
        "deliveryMethod": {"const": "sync"},
        "includeCost": {"type": "boolean"},
        "settings": {"type": "object"},
        "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647},
    }
    if negative:
        properties["negativePrompt"] = {"type": "string"}
    # Without the named field a request's references still validate, as a model's other
    # input fields would: only the ability to take a still changes.
    properties["inputs"] = {
        "type": "object",
        "properties": {
            ("referenceImages" if references else "styleImages"): {
                "type": "array",
                "maxItems": 14,
                "items": {"type": "string"},
            }
        },
    }
    return {
        "info": {"x-status": "live", "x-air-id": air, "x-pricing": {"measured": "0.034"}},
        "components": {
            "schemas": {
                "RequestBody": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["taskType", "taskUUID", "model", "positivePrompt"],
                        "additionalProperties": False,
                        "properties": properties,
                    },
                }
            }
        },
    }


def jpeg_at(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), (40, 80, 120)).save(path, "JPEG")
