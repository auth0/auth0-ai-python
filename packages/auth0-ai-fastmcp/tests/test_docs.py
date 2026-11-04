"""Every Python snippet in the README and guides parses, and the names it imports from our packages exist."""

import ast
import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"^```python\n(.*?)^```", re.DOTALL | re.MULTILINE)
CHECKED_PACKAGES = ("auth0_ai_fastmcp", "auth0_ai_mcp", "fastmcp")
SIGNATURE = re.compile(r"^[\w.]+\(.*\) -> ", re.MULTILINE)


def _snippets():
    for path in [ROOT / "README.md", ROOT / "EXAMPLES.md", *sorted((ROOT / "docs").glob("*.md"))]:
        for index, match in enumerate(FENCE.finditer(path.read_text()), start=1):
            yield pytest.param(match.group(1), id=f"{path.relative_to(ROOT)}#{index}")


@pytest.mark.parametrize("source", _snippets())
def test_doc_snippet_parses_and_imports_exist(source):
    if SIGNATURE.match(source) and len(source.strip().splitlines()) == 1:
        pytest.skip("method signature shown for reference, not runnable code")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in CHECKED_PACKAGES:
            module = importlib.import_module(node.module)
            missing = [alias.name for alias in node.names if not hasattr(module, alias.name)]
            assert not missing, f"{node.module} has no {missing}"
