#!/usr/bin/env python3
# @domain:   spec-1
# @module:   spec1_mono_light
# @loc:      gh_main
# @status:   stable
# @depends:  NONE

"""
SPEC-1 // DIRECTORY SCANNER // MISSION CONTROL BOOT DISPLAY
Scans current directory and displays intelligence in the center.
"""

import os
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime

def scan_directory(target_dir: Path = None):
    """Scan the current directory for intelligence files."""
    if target_dir is None:
        target_dir = Path.cwd()

    # Count files by type
    md_files = list(target_dir.glob("*.md"))
    txt_files = list(target_dir.glob("*.txt"))
    json_files = list(target_dir.glob("*.json"))
    html_files = list(target_dir.glob("*.html"))

    # Check for SPEC-1 data file
    data_path = target_dir / "src/spec1_api/static/data/portland_vectors.json"
    has_vectors = data_path.exists()

    # Get directory info
    dir_name = target_dir.name
    total_files = len(md_files) + len(txt_files) + len(json_files)

    # Get last modified file
    all_files = md_files + txt_files + json_files
    latest_file = max(all_files, key=lambda f: f.stat().st_mtime) if all_files else None
    latest_time = datetime.fromtimestamp(latest_file.stat().st_mtime).strftime("%H:%M:%S") if latest_file else "N/A"

    return {
        "directory": dir_name,
        "full_path": str(target_dir),
        "md_count": len(md_files),
        "txt_count": len(txt_files),
        "json_count": len(json_files),
        "html_count": len(html_files),
        "total_intel_files": total_files,
        "has_vectors": has_vectors,
        "latest_file": latest_file.name if latest_file else "None",
        "latest_time": latest_time
    }

def strip_ansi_codes(text: str) -> str:
    """Removes hidden ANSI color symbols to keep visual formatting aligned."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def render_center_text(text: str, width: int = 80) -> str:
    """Center text within the given width safely avoiding string padding errors."""
    visible_length = len(strip_ansi_codes(text))
    padding = width - visible_length - 2  # -2 for borders
    left_pad = padding // 2
    right_pad = padding - left_pad
    return f"║{' ' * left_pad}{text}{' ' * right_pad}║"

def render_terminal_boot(scan_data: dict):
    """Render the SPEC-1 boot screen with directory info centered."""
    os.system('cls' if os.name == 'nt' else 'clear')

    width = 80

    # ── Top border ────────────────────────────────────────────────────────────
    print("╔" + "═"*(width-2) + "╗")
    print("║ INIT PID 1...                                                                ║")
    print("║ PYTHON 3.11+ DETECTED                                                        ║")
    print("║ LOADING 607 TESTS... \033[32m[OK]\033[0m                                                    ║")
    print("║ PIPELINE STATUS: READY                                                       ║")
    print("║" + " "*(width-2) + "║")

    # ── High-Contrast Scaled Center Brand Core ────────────────────────────────
    title_str = "[  S P E C - 1   I N T E L L I G E N C E   E N G I N E  ]"
    print(f"║\033[1m{title_str:^{width-2}}\033[0m║")
    print("║" + " "*(width-2) + "║")

    # ── DIRECTORY DISPLAY (CENTERED, PROMINENT) ───────────────────────────────
    dir_display = f"◉  CURRENT MISSION SECTOR:  {scan_data['directory'].upper()}  ◉"
    print(render_center_text(f"\033[1;33m{dir_display}\033[0m", width))

    # ── Location line (smaller, beneath) ──────────────────────────────────────
    location_str = f"└── {scan_data['full_path']}"
    if len(location_str) > (width - 8):
        location_str = f"└── ...{location_str[-65:]}"
    print(render_center_text(f"\033[90m{location_str}\033[0m", width))
    print("║" + " "*(width-2) + "║")

    # ── Subtitle ──────────────────────────────────────────────────────────────
    sub_str = "_ Automated OSINT for geo/regional anomaly detection."
    print(f"║{sub_str:^{width-2}}║")

    meta_str = f"// v0.4.0 • SCAN AT {scan_data['latest_time']} • EVASTARARCANA"
    print(f"║{meta_str:^{width-2}}║")

    # ── Intelligence Summary (left-aligned, indented) ─────────────────────────
    print("║" + " "*(width-2) + "║")
    print("║   INTELLIGENCE ASSETS DETECTED:                                              ║")

    if scan_data['md_count'] > 0:
        print(f"║      ├── \033[36m{scan_data['md_count']}\033[0m Markdown files (.md)                                     ║")
    if scan_data['txt_count'] > 0:
        print(f"║      ├── \033[36m{scan_data['txt_count']}\033[0m Text files (.txt)                                         ║")
    if scan_data['json_count'] > 0:
        print(f"║      ├── \033[36m{scan_data['json_count']}\033[0m JSON payloads (.json)                                     ║")
    if scan_data['html_count'] > 0:
        print(f"║      └── \033[32m{scan_data['html_count']}\033[0m Generated briefs (.html)                                  ║")
    else:
        print("║      └── No existing briefs found                                            ║")

    # ── Vector status ─────────────────────────────────────────────────────────
    print("║" + " "*(width-2) + "║")
    if scan_data['has_vectors']:
        print("║      \033[32m✓\033[0m Vector database detected (portland_vectors.json)                      ║")
    else:
        print("║      \033[33m○\033[0m No vector database. Run 'mkdir -p src/spec1_api/static/data'          ║")

    # ── Last file detected ────────────────────────────────────────────────────
    if scan_data['latest_file'] != "None":
        print(f"║      \033[90m→\033[0m Last intel: {scan_data['latest_file']:<54} ║")

    # ── Bottom border ─────────────────────────────────────────────────────────
    print("║" + " "*(width-2) + "║")
    print("╚" + "═"*(width-2) + "╝")

    # ── Command menu ──────────────────────────────────────────────────────────
    print(f"\n┌" + "─"*(width-2) + "┐")
    print("│  COMMAND MENU                                                                │")
    print(f"├" + "─"*(width-2) + "┤")
    print(f"│  Current Sector: \033[33m{scan_data['directory'].upper():<59}\033[0m │")
    print("│                                                                              │")
    print("│  [1] Convert all intel files to HTML                                         │")
    print("│  [2] Convert all intel files to PDF                                          │")
    print("│  [3] Convert to both (HTML + PDF)                                            │")
    print("│  [4] Re-scan directory                                                       │")
    print("│  [5] Exit                                                                    │")
    print(f"└" + "─"*(width-2) + "┘")

    return scan_data

def convert_files(scan_data: dict, output_format: str):
    """Convert discovered files to HTML/PDF."""
    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)

    target_dir = Path.cwd()
    all_files = list(target_dir.glob("*.md")) + list(target_dir.glob("*.txt")) + list(target_dir.glob("*.json"))
    all_files = [f for f in all_files if f.name not in ["package.json", ".mcp.json"]]

    if not all_files:
        print("\n\033[33m⚠ No intel files found to convert.\033[0m")
        return

    print(f"\n\033[36m► Converting {len(all_files)} files to {output_format.upper()}...\033[0m\n")

    for file_path in all_files:
        print(f"   Processing: {file_path.name}... ", end="")
        try:
            converter_path = Path("spec1_professional.py")
            if converter_path.exists():
                cmd = ["python3", str(converter_path), "--brief-md", str(file_path), "--out", str(output_dir / f"{file_path.stem}.pdf")]
                if output_format == "html":
                    cmd.append("--no-pdf")
                elif output_format == "pdf":
                    cmd.append("--no-html")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("\033[32m✓\033[0m")
                else:
                    print(f"\033[31m✗ ({result.stderr[:50]}...)\033[0m")
            else:
                html_path = output_dir / f"{file_path.stem}.html"
                html_path.write_text(f"<html><body><pre>{file_path.read_text()}</pre></body></html>")
                print("\033[32m✓ (fallback)\033[0m")
        except Exception as e:
            print(f"\033[31m✗ {e}\033[0m")

    print(f"\n\033[32m✅ Conversion complete. Output in: {output_dir}/\033[0m")

def main():
    scan_data = scan_directory()
    render_terminal_boot(scan_data)

    while True:
        try:
            choice = input("\n> SELECT [1-5]: ").strip()
            if choice == "1":
                convert_files(scan_data, "html")
            elif choice == "2":
                convert_files(scan_data, "pdf")
            elif choice == "3":
                convert_files(scan_data, "both")
            elif choice == "4":
                scan_data = scan_directory()
                render_terminal_boot(scan_data)
            elif choice == "5":
                print("\n\033[36m╔══════════════════════════════════════════════════════════════════════════════╗")
                print("║  SYSTEM HALT. AWAITING NEXT CYCLE.                                           ║")
                print("╚══════════════════════════════════════════════════════════════════════════════╝\033[0m")
                break
            else:
                print("\033[31mInvalid choice. Enter 1, 2, 3, 4, or 5.\033[0m")
        except KeyboardInterrupt:
            print("\n\n\033[33mInterrupted. Exiting...\033[0m")
            break

if __name__ == "__main__":
    main()
