import sys
import time
import math

def draw_retro_radar_sweep():
    # Clear terminal using ANSI escape sequences (avoids subprocess shell invocation)
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    # Establish radar sweep radius and center coordinates
    width, height = 70, 22
    cx, cy = width // 2, height // 2
    radius = min(cx, cy) - 2

    # Tactical Amber/Green Phosphor character density map
    angle = 0.0

    try:
        print("\033[?25l") # Hide terminal cursor block to prevent screen flickering
        while True:
            # Build an empty frame buffer
            buffer = [[" " for _ in range(width)] for _ in range(height)]

            # 1. Plot circular target tracking rings
            for y in range(height):
                for x in range(width):
                    # Adjust for standard terminal character aspect ratios (2:1 vertical stretch)
                    dx = (x - cx) * 0.5
                    dy = y - cy
                    dist = math.sqrt(dx*dx + dy*dy)

                    if abs(dist - radius) < 0.5 or abs(dist - radius/2) < 0.5:
                        buffer[y][x] = "\033[32m·\033[0m" # Dim target rings

            # 2. Compute live radar sweep line positions
            sweep_x = cx + int(radius * 2.0 * math.cos(angle))
            sweep_y = cy + int(radius * math.sin(angle))

            # Draw the active beam trailing sweep path
            for step in range(radius):
                t = step / radius
                px = cx + int(radius * 2.0 * math.cos(angle - 0.1) * t)
                py = cy + int(radius * math.sin(angle - 0.1) * t)
                if 0 <= px < width and 0 <= py < height:
                    buffer[py][px] = "\033[32m:\033[0m"

            if 0 <= sweep_x < width and 0 <= sweep_y < height:
                buffer[sweep_y][sweep_x] = "\033[1;33m█\033[0m" # High-intensity active target node

            # ── Render Frame Buffer to Terminal Screen ────────────────────────
            output = []
            output.append("+" + "-" * width + "+")
            output.append("| SPEC-1 TACTICAL SIGNAL TARGET LOG // RADAR STREAM ACTIVE              |")
            output.append("+" + "-" * width + "+")

            for row in buffer:
                output.append("|" + "".join(row) + "|")

            output.append("+" + "-" * width + "+")
            output.append("| COMMANDS: [Ctrl+C] Terminate Console Sweep Run                        |")
            output.append("+" + "-" * width + "+")

            # Reset screen cursor position instantly instead of clearing to avoid flicker
            sys.stdout.write("\033[H" + "\n".join(output))
            sys.stdout.flush()

            angle += 0.08
            time.sleep(0.04)

    except KeyboardInterrupt:
        print("\033[?25h\n\n// SPEC-1 // System interface sweep suspended cleanly.\n")

if __name__ == "__main__":
    draw_retro_radar_sweep()
