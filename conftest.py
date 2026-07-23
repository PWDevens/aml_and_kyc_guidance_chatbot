# Repo-root conftest so the test suite is importable under a bare `pytest`
# invocation, not only `python -m pytest`.
#
# The tests import the project code by its top-level package name
# (`from src.rag.config import CONFIG`, `from src.app import api`, ...). Under
# pytest's default "prepend" import mode, pytest adds the first parent
# directory *without* an `__init__.py` to sys.path. `tests/` has no
# `__init__.py`, so for a file like tests/test_smoke.py pytest would prepend
# `tests/` — never the repo root — and `import src` fails with
# ModuleNotFoundError. `python -m pytest` happened to mask this locally because
# `-m` also prepends the current working directory (the repo root) to sys.path;
# the bare `pytest tests/ -q` used by .github/workflows/ci.yml and the Docker
# image does not, which is why hosted CI failed at collection with
# "No module named 'src'".
#
# Because pytest also collects this top-level conftest.py, its own basedir (the
# repo root, which has no __init__.py) is prepended to sys.path during
# collection. That single side effect makes `import src` resolve for every
# invocation form (bare `pytest`, `python -m pytest`, CI, and the container),
# which is exactly what we want and why this file is intentionally otherwise
# empty.
