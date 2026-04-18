"""Allow ``python -m depos.cli ...`` invocation, same as the
``depos-intel`` console script."""
from __future__ import annotations

import sys

from depos.cli import main


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
