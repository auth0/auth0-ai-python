"""Every Python snippet in the README and guides parses, imports names that exist, and builds `Auth0FastMCPOptions` with real fields."""

import ast
import dataclasses
import importlib
import re
from pathlib import Path

import pytest

from auth0_ai_fastmcp import Auth0FastMCPOptions

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"^```python\n(.*?)^```", re.DOTALL | re.MULTILINE)
CHECKED_PACKAGES = ("auth0_ai_fastmcp", "auth0_ai_mcp", "fastmcp")
OPTION_FIELDS = {field.name for field in dataclasses.fields(Auth0FastMCPOptions)}


def _snippets():
    for path in [ROOT / "README.md", ROOT / "EXAMPLES.md", *sorted((ROOT / "docs").glob("*.md"))]:
        for index, match in enumerate(FENCE.finditer(path.read_text()), start=1):
            yield pytest.param(match.group(1), id=f"{path.relative_to(ROOT)}#{index}")


@pytest.mark.parametrize("source", _snippets())
def test_doc_snippet_parses_and_imports_exist(source):
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in CHECKED_PACKAGES:
                    importlib.import_module(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in CHECKED_PACKAGES:
            module = importlib.import_module(node.module)
            missing = [alias.name for alias in node.names if not hasattr(module, alias.name)]
            assert not missing, f"{node.module} has no {missing}"


@pytest.mark.parametrize("source", _snippets())
def test_doc_snippet_options_use_real_fields(source):
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Auth0FastMCPOptions":
            unknown = [kw.arg for kw in node.keywords if kw.arg and kw.arg not in OPTION_FIELDS]
            assert not unknown, f"Auth0FastMCPOptions has no field {unknown}"


def test_docs_have_python_snippets():
    assert list(_snippets())
