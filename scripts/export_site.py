#!/usr/bin/env python3
"""Export the web app's JSON from the site marts (`site.*`).

Delegates to `scripts/export_data.py`, which is the primary site exporter as of
data-layers step 19.

    uv run python scripts/export_site.py --out <dir>
"""
import sys
import export_data

if __name__ == "__main__":
    sys.exit(export_data.main())
