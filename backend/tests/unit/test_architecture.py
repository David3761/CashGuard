"""F1.3: time comes only from `app.clock` (work-breakdown 0.3 rule 3: it makes the sim work).

Two independent guards: ruff's banned-API rule TID251 (pyproject), and an AST scan of `app/` that
also works if the lint config changes. Both allow `app/clock.py` and nothing else, and both use
the same list: the one in pyproject.toml.

The scan resolves import aliases (`from datetime import datetime as D`, `import time as t`) and
flags *references*, not only calls (`Field(default_factory=datetime.now)`, SQLAlchemy
`default=datetime.now`), star imports of `time` / `datetime`, and `getattr(<datetime-ish>, "now")`
with a literal name. Out of scope (ruff doesn't see these either): `importlib` / `__import__`,
`getattr` with a computed name, `eval`, and a wall-clock function handed over from another module.
"""

import ast
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from app.config import BACKEND_DIR

APP_DIR = BACKEND_DIR / "app"
_LINT = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["ruff"]
BANNED = frozenset(_LINT["lint"]["flake8-tidy-imports"]["banned-api"])  # e.g. "time.time"
WALL_CLOCK_MODULES = frozenset({"datetime", "time"})


def _qualified(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """The fully qualified name of `D.now`, `t.time`, `time` …, resolved through the imports."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _qualified(node.value, aliases)
        return f"{base}.{node.attr}" if base else None
    return None


def _wall_clock_reads_in(tree: ast.Module) -> list[tuple[int, str]]:
    aliases: dict[str, str] = {}  # local name -> qualified name
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in WALL_CLOCK_MODULES:
            for alias in node.names:
                qualified = f"{node.module}.{alias.name}"
                if alias.name == "*":
                    found.append((node.lineno, f"from {node.module} import *"))
                elif qualified in BANNED:
                    found.append((node.lineno, f"from {node.module} import {alias.name}"))
                aliases[alias.asname or alias.name] = qualified
    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Attribute) and _qualified(node, aliases) in BANNED:
            found.append((node.lineno, f"{ast.unparse(node)} ({_qualified(node, aliases)})"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            base = _qualified(node.args[0], aliases)
            if base and f"{base}.{node.args[1].value}" in BANNED:
                found.append((node.lineno, f"{ast.unparse(node)} ({base}.{node.args[1].value})"))
    return sorted(set(found))


def find_wall_clock_reads(root: Path) -> list[str]:
    """`file:line: what` for every wall-clock read under `root`, except in `clock.py`."""
    found = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if relative == Path("clock.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found += [f"{relative}:{line}: {what}" for line, what in _wall_clock_reads_in(tree)]
    return found


def test_the_banned_list_is_the_lint_config() -> None:
    # Mirrors pyproject (6a625fd); `time.monotonic` / `perf_counter` stay allowed (durations).
    assert (
        frozenset(
            {
                "datetime.datetime.now",
                "datetime.datetime.utcnow",
                "datetime.datetime.today",
                "datetime.date.today",
                "time.time",
                "time.time_ns",
                "time.localtime",
                "time.gmtime",
                "time.strftime",
                "time.ctime",
                "time.asctime",
                "time.clock_gettime",
                "time.clock_gettime_ns",
            }
        )
        == BANNED
    )


def test_the_app_reads_the_wall_clock_only_in_clock_py() -> None:
    assert find_wall_clock_reads(APP_DIR) == []


def test_the_scan_finds_every_banned_read(tmp_path: Path) -> None:
    # Proves the guard above can fail: planted reads in every form, and the one allowed file.
    (tmp_path / "pipeline").mkdir()
    (tmp_path / "pipeline" / "jobs.py").write_text(
        '"""Never call datetime.now() here."""  # a mention, not a read\n'
        "import datetime as dt\n"
        "import time\n"
        "import time as t\n"
        "from datetime import date, datetime\n"
        "from datetime import datetime as D\n"
        "from time import time_ns\n"
        "# datetime.now() in a comment is fine\n"
        "a = datetime.now()\n"
        "b = dt.datetime.utcnow()\n"
        "c = date.today()\n"
        "d = D.today()\n"
        "e = t.time()\n"
        "f = time_ns()\n"
        "g = time.monotonic()\n"
        "h = time.localtime()\n"
        "i = Field(default_factory=datetime.now)\n"
        "j = Column(default=D.now)\n"
        "k = getattr(D, 'now')()\n"
        "m = getattr(t, 'clock_gettime')(0)\n"
        "n = datetime.fromisoformat('2026-06-15T09:00:00Z')\n"
    )
    (tmp_path / "stars.py").write_text("from time import *\nfrom datetime import *\nx = time()\n")
    (tmp_path / "clock.py").write_text("from datetime import datetime\nx = datetime.now()\n")

    assert find_wall_clock_reads(tmp_path) == [
        "pipeline/jobs.py:7: from time import time_ns",
        "pipeline/jobs.py:9: datetime.now (datetime.datetime.now)",
        "pipeline/jobs.py:10: dt.datetime.utcnow (datetime.datetime.utcnow)",
        "pipeline/jobs.py:11: date.today (datetime.date.today)",
        "pipeline/jobs.py:12: D.today (datetime.datetime.today)",
        "pipeline/jobs.py:13: t.time (time.time)",
        "pipeline/jobs.py:14: time_ns (time.time_ns)",
        "pipeline/jobs.py:16: time.localtime (time.localtime)",
        "pipeline/jobs.py:17: datetime.now (datetime.datetime.now)",
        "pipeline/jobs.py:18: D.now (datetime.datetime.now)",
        "pipeline/jobs.py:19: getattr(D, 'now') (datetime.datetime.now)",
        "pipeline/jobs.py:20: getattr(t, 'clock_gettime') (time.clock_gettime)",
        "stars.py:1: from time import *",
        "stars.py:2: from datetime import *",
    ]


PROBE = "import datetime\nimport time\n" + "".join(
    f"x{index} = {name}()\n" for index, name in enumerate(sorted(BANNED))
)


def _ruff_banned_api_findings(as_file: str) -> list[str]:
    """Run ruff on PROBE as if it were `as_file` (so the project's per-file rules apply)."""
    result = subprocess.run(  # noqa: S603 - our own interpreter running ruff on a fixed snippet
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--select",
            "TID251",
            "--output-format",
            "json",
            "--stdin-filename",
            as_file,
            "-",
        ],
        input=PROBE,
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr  # 0 clean, 1 findings, 2 ruff error
    return [finding["message"] for finding in json.loads(result.stdout)]


@pytest.mark.parametrize("as_file", ["app/pipeline/jobs.py", "tests/unit/test_x.py"])
def test_ruff_bans_every_wall_clock_read_outside_clock_py(as_file: str) -> None:
    messages = _ruff_banned_api_findings(as_file)

    assert {m.split("` is banned")[0].lstrip("`") for m in messages} == BANNED
    assert len(messages) == len(BANNED)


def test_ruff_allows_them_in_clock_py() -> None:
    assert _ruff_banned_api_findings("app/clock.py") == []
