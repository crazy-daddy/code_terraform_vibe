# Data Archive Cleaner & Validator Executable
# Run this script on any computer or terminal to inspect, validate, repair,
# and prune stale or corrupted entries in the shared Data Archive ('notebook').

from archive_cleaner import ArchiveCleaner

# Set DRY_RUN = True to preview changes without deleting
DRY_RUN = False

cleaner = ArchiveCleaner(dry_run=DRY_RUN, verbose=True)
cleaner.run()
