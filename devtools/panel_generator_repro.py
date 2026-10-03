# In-game script: the game injects `panel`, which devtools/ Pyright does not see.
# pyright: reportUndefinedVariable=false
# Minimal repro (fixed in game v0.1.29, kept as a regression check): a suspended generator disconnected a panel script from its card.
#
# Paste into an empty Custom Panel, set MODE, run. Use a fresh card per run (or
# run "none" first) so a leftover frame is not mistaken for a frozen one.
#
#   "none"   no generator, no exception. Card counts up.
#   "any"    any() stops at the first match and leaves its generator suspended.
#            Card freezes: not even panel.clear() lands, while the console keeps
#            printing "still looping".
#   "alive"  generator suspended by next() and kept referenced. Card freezes.
#   "closed" same, then g.close(). Card counts up.
#   "caught" a raised and caught ValueError, no generator. Card counts up.
#
# So a generator left suspended detaches the card; closing it releases the
# card, and exceptions play no part. An unreferenced generator (the "any" case)
# is never closed on its own.
#
# The card and the console both show panel.width() x panel.height(), to check
# whether reads still work while draws are lost.
MODE = "any"

if MODE == "any":
    any(x > 0 for x in [1, 2, 3])
elif MODE == "alive":
    g = (x for x in [1, 2, 3])
    next(g)
elif MODE == "closed":
    g = (x for x in [1, 2, 3])
    next(g)
    g.close()
elif MODE == "caught":
    try:
        raise ValueError("probe")
    except ValueError:
        pass

loops = 0
while True:
    loops += 1
    size = f"{panel.width()}x{panel.height()}"
    panel.clear()
    panel.draw_text(20, 40, f"{MODE} loop {loops} {size}", 16, "text-bright")
    if loops % 500 == 0:
        print(f"{MODE} still looping: {loops} {size}")
