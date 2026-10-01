# @domain:  spec-1
# @module:  local_terminal_monitor
# @loc:     gh_main
# @status:  stable

import curses
import time
import random
from datetime import datetime

def run_monitor(stdscr):
    # Hide cursor and set non-blocking input
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(1000) # Refresh loop rate: 1000ms
    
    # Initialize basic color pairs if supported
    if curses.has_colors():
        curses.start_color()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE) # Inverted
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK) # Standard
        
    # Mock log stream data to simulate pipeline activity
    log_pool = [
        "HARVESTER: RSS cycle initialized successfully.",
        "DB_WRITE: 14 rows committed to PostgreSQL pipeline.",
        "COUPLER: Signal match found in US economic region 4.",
        "SWITCHBOARD: Ingesting active city-level feeds.",
        "SYS_CORE: Token parsimony verification check passed.",
        "GOSINT: Processing supply chain metrics...",
        "ANALYST_LOOP: Awaiting manual promotion flag."
    ]
    logs = ["MONITOR START: Standing by for system signals..."]

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        
        # Enforce minimum terminal size window
        if height < 20 or width < 70:
            stdscr.addstr(0, 0, "TERMINAL WINDOW TOO SMALL. EXPAND WINDOW TO VIEW FEED.")
            stdscr.refresh()
            time.sleep(0.2)
            continue

        # --- HEADER BLOCK ---
        stdscr.attron(curses.color_pair(1))
        header_text = " SPEC-1 // OPERATIONAL SIGNAL FEED "
        stdscr.addstr(1, 2, header_text + " " * (width - len(header_text) - 4))
        stdscr.attroff(curses.color_pair(1))
        
        # --- METADATA ROW ---
        meta_str = f"TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  REPO: develop  |  LOC: _SCRATCH  |  STATUS: ACTIVE"
        stdscr.addstr(3, 2, meta_str, curses.A_DIM)
        stdscr.addstr(4, 2, "─" * (width - 4), curses.A_DIM)

        # --- LEFT PANEL: ACTIVE DOMAINS & CONCEPT MATRIX ---
        stdscr.addstr(6, 2, "► CONCEPT MATRIX OVERVIEW", curses.A_BOLD)
        
        matrix_data = [
            ("spec-1", "project_prompt", "claude_cloud", "STABLE"),
            ("spec-1", "postgres_schema", "_SCRATCH", "TESTING"),
            ("gosint", "supply_chain_r4", "gh_main", "STABLE"),
            ("switchboard", "cls_metro_pdx", "_SCRATCH", "DRAFTING")
        ]
        
        stdscr.addstr(8, 2, f"{'DOMAIN':<14} {'MODULE':<18} {'LOC':<14} {'STATUS'}", curses.A_UNDERLINE)
        for idx, (dom, mod, loc, stat) in enumerate(matrix_data):
            stdscr.addstr(9 + idx, 2, f"{dom:<14} {mod:<18} {loc:<14} {stat}")

        # --- RIGHT PANEL: LIVE SIGNAL STREAM (APPEND-ONLY) ---
        stdscr.addstr(6, width // 2, "► LIVE SIGNAL LOG (STAGING)", curses.A_BOLD)
        
        # Randomly inject incoming traffic to simulate actual pipeline flow
        if random.random() > 0.6:
            timestamp = datetime.now().strftime("%H:%M:%S")
            new_log = f"[{timestamp}] {random.choice(log_pool)}"
            logs.append(new_log)
            if len(logs) > (height - 10): # Prevent log overflow
                logs.pop(0)
                
        for idx, log_line in enumerate(logs[-(height - 10):]):
            stdscr.addstr(8 + idx, width // 2, log_line[:width // 2 - 4])

        # --- FOOTER ---
        stdscr.addstr(height - 2, 2, "─" * (width - 4), curses.A_DIM)
        stdscr.addstr(height - 1, 2, "Press [Q] or [Ctrl+C] to terminate visualizer feed.", curses.A_DIM)
        
        stdscr.refresh()

        # Check for termination key exit
        try:
            key = stdscr.getch()
            if key in [ord('q'), ord('Q')]:
                break
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    curses.wrapper(run_monitor)
