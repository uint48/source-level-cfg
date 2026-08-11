#!/usr/bin/env python3
"""Regenerate the golden CFGs under tests/golden/.

Run this only after reviewing the new graphs -- the goldens are the record of
what has been checked by hand, so overwriting them without looking defeats their
purpose.

    python tests/regen_golden.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.helpers import canonical_for, sample_paths, write_golden  # noqa: E402


def main():
    for java_path in sample_paths():
        data = canonical_for(java_path)
        write_golden(java_path, data)
        methods = len(data)
        print(f"{java_path.name}: {methods} method(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
