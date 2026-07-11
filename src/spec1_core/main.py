# @domain:   machine
# @module:   main
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""SPEC-1 entry point.

Usage:
    python -m spec1_core.main
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv(encoding="utf-8-sig")  # utf-8-sig strips PowerShell BOM if present

import uvicorn


def main() -> None:
    uvicorn.run(
        "spec1_core.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
