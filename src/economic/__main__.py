"""Allow ``python -m economic`` as well as the installed ``economic`` script.

Continuous integration and scripted use should not depend on a console-script
shim being on PATH.
"""

from .cli.main import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
