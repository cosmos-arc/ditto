"""Zero-dependency entry point shipped inside every release cohort bundle."""

from __future__ import annotations

from tooling.release.cohort_verify import main

if __name__ == "__main__":
    raise SystemExit(main())
