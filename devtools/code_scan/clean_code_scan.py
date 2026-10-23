"""
Clean-code scans over scripts/, one entry point.

    python devtools/code_scan/clean_code_scan.py clones [options]     # near-duplicate functions (clone_scan.py)
    python devtools/code_scan/clean_code_scan.py features [options]   # code that a supported interpreter feature would simplify (feature_scan.py)
    python devtools/code_scan/clean_code_scan.py size [options]       # long files and complex functions (size_scan.py)
    python devtools/code_scan/clean_code_scan.py <scan> -h            # options and details of one scan

All scan the same files (scan_common.scanned_files()), except clone_scan.py, which also
scans autoplay/; all keep reviewed
"leave as is" verdicts in their own ignore file, so a rerun lists only new
candidates. Every hit is a candidate: read the code before changing it.
"""

import argparse

import clone_scan
import feature_scan
import size_scan

SCANS = {
    "clones": (clone_scan, "near-duplicate functions, candidates for one shared helper"),
    "features": (feature_scan, "code that a supported interpreter feature would simplify"),
    "size": (size_scan, "long files and complex functions, a smell to look at"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="scan", required=True)
    for name, (module, summary) in SCANS.items():
        scan_parser = sub.add_parser(
            name, description=module.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, help=summary
        )
        module.add_arguments(scan_parser)
    args = parser.parse_args()
    SCANS[args.scan][0].run(args)


if __name__ == "__main__":
    main()
