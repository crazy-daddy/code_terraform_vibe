# ct-automation: infra_planner_automation
# Infrastructure planner -- an Automation (Computer > Automations): belongs to
# no machine and draws no power. Runs every planner pass (autoplay/lib/planner_loop.py):
# outpost founding (map markers), building proposals (BUILD card), then power
# links, per-fluid pipe networks and extractors as construction blueprints for
# Pioneers. Never ends: once the infrastructure is done it keeps watching the
# outposts. Deployed only with `scripts_sync.py ... --include-autoplay`.
from planner_loop import run_planner

run_planner()
