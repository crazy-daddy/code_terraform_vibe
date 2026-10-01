# Word wrap for Custom Panel text: panel.draw_text() draws one line and clips
# at the card edge, so long status text is split by an estimated character
# width (font size 10) before drawing.

# Rendered width of one font-size-10 character, in panel pixels.
TEXT_CHAR_PX = 7
# Line pitch for font-size-10 text.
TEXT_LINE_PX = 13


def wrap_text(text, width_px, max_lines, char_px=TEXT_CHAR_PX):
    """text word-wrapped into at most max_lines lines of width_px; an overlong word or the last kept line is cut with ".."."""
    chars = int(width_px // char_px)
    if chars <= 2:
        return []
    lines, line = [], ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if len(candidate) <= chars or not line:
            line = candidate
            continue
        lines.append(line)
        line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:chars - 2] + ".."
    return [l if len(l) <= chars else l[:chars - 2] + ".." for l in lines]
