#!/usr/bin/env python3
import sys

# Try to import the package when running from source or after installation
try:
    from fixedrec.cli import main
except Exception:
    # Fallback: when running from repo without installation, adjust sys.path
    import os
    repo_root = os.path.dirname(__file__)
    sys.path.insert(0, repo_root)
    from fixedrec.cli import main


if __name__ == "__main__":
    sys.exit(main())
