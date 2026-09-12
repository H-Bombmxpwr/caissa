"""Sphinx configuration for the Caissa documentation site.

Built by .github/workflows/docs.yml and published to GitHub Pages. Prose is written
in MyST Markdown so it reads the same on GitHub as it does on the site; the API
reference is generated from the backend's own docstrings, so it cannot drift from
the code the way a hand-written one does.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath('..'))

project = 'Caissa'
author = 'Hunter'
copyright = '%d, %s' % (date.today().year, author)
release = '2.0'

extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
    'sphinx.ext.autosummary',
    'sphinx_copybutton',
    'sphinx_design',
    'sphinxcontrib.mermaid',
]

myst_enable_extensions = ['colon_fence', 'deflist', 'substitution', 'attrs_inline']
myst_heading_anchors = 3

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
source_suffix = {'.md': 'markdown', '.rst': 'restructuredtext'}

autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'member-order': 'bysource',
    'show-inheritance': True,
}
autodoc_mock_imports = ['psutil', 'webview', 'zstandard']
autosummary_generate = True
napoleon_google_docstring = True

intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}

html_theme = 'furo'
html_title = 'Caissa'
html_static_path = ['_static']
html_logo = '_static/caissa.png'
html_favicon = '_static/caissa.png'
html_copy_source = False
html_theme_options = {
    'sidebar_hide_name': True,
    'light_css_variables': {
        'color-brand-primary': '#315e48',
        'color-brand-content': '#315e48',
    },
    'dark_css_variables': {
        'color-brand-primary': '#8fc0a0',
        'color-brand-content': '#8fc0a0',
    },
}
