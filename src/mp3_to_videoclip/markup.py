"""One escaping policy for every generated page.

These pages interpolate artifact data into markup, and two of them embed JSON in a
``<script>`` element. Both operations belong in one place so a new page cannot
quietly omit either the HTML escape or the ``</`` mitigation that stops a value
from closing its own script tag.
"""

from __future__ import annotations

import html as _html
import json


def esc(value) -> str:
    """Escape one value for HTML text or a quoted attribute; ``None`` is empty."""
    return _html.escape("" if value is None else str(value))


def script_json(payload, **kwargs) -> str:
    """Compact JSON that is safe inside ``<script>`` (no premature ``</script>``)."""
    kwargs.setdefault("separators", (",", ":"))
    return json.dumps(payload, **kwargs).replace("</", "<\\/")
