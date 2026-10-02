# ct-automation: outpost_planner_automation
# Outpost founding planner alone -- an Automation (Computer > Automations):
# needs, site ranking and outpost proposals as map markers, read back from the
# operator's answers; no power, pipe or extractor passes. Ends once no
# proposal waits. Do not run beside infra_planner_automation (same proposals
# and markers). Deployed only with `scripts_sync.py ... --include-autoplay`.
from planner_loop import run_founding
run_founding()
