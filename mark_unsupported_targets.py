# Map Markers from Unsupported Targets
# Thin entrypoint over lib/unsupported_markers.py -- run manually to sync
# survey.unsupported_targets to Planet Map markers. Also available as a
# "Sync Unsupported" button in panel_1.py's AUTOMATION section.

from unsupported_markers import update_unsupported_markers

update_unsupported_markers(clear_previous=True)
