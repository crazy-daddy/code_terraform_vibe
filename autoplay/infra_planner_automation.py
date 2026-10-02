# ct-automation: infra_planner_automation
# Infrastructure planner -- an Automation (Computer > Automations): belongs to
# no machine and draws no power. Plans power links (later: extractors and pipe
# networks) as construction blueprints for Pioneers, then ends once nothing is
# left to plan. Deployed only with `scripts_sync.py ... --include-autoplay`.
from planner_loop import run_planner
run_planner()
