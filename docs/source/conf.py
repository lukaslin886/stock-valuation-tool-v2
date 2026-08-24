"""Sphinx configuration for stock-valuation-tool."""

import os
import sys
from datetime import datetime

DOCS_SOURCE_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(DOCS_SOURCE_DIR, "..", ".."))
APP_ROOT = os.path.join(REPO_ROOT, "app")

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, APP_ROOT)

project = "Stock Valuation Tool"
author = "AI Collaborative Development"
copyright = f"{datetime.now().year}, {author}"
release = "v1.9.3"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.autosummary",
]

autosummary_generate = True
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"

# Keep API docs build-stable in environments where optional data sources are absent.
autodoc_mock_imports = [
    "finlab",
    "finmind",
    "FinMind",
    "yfinance",
    "streamlit",
    "plotly",
    "matplotlib",
    "seaborn",
    "scipy",
    "reportlab",
    "PIL",
]

napoleon_google_docstring = True
napoleon_numpy_docstring = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
language = "zh_TW"

html_theme = "alabaster"
html_static_path = ["_static"]
html_title = "Stock Valuation Tool API Docs"
