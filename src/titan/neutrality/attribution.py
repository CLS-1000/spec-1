# @domain:   citizens_source
# @module:   neutrality_attribution
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""Attribution gate: every factual claim must carry a source URI."""

from __future__ import annotations

import re
from typing import Optional

_URL_RE = re.compile(r"https?://\S+")


def attribution_gate(text: str, source_uri: str) -> tuple[bool, Optional[str]]:
    """Fail if source_uri is absent or not a valid HTTP(S) URL."""
    if not source_uri or not source_uri.startswith(("http://", "https://")):
        return False, f"ATTR_001: section lacks valid source_uri: {source_uri!r}"
    return True, None
