# Configuration file for Sphinx to build our documentation to HTML.
#
# Configuration reference: https://www.sphinx-doc.org/en/master/usage/configuration.html
#
import datetime

import kubespawner

# -- Project information -----------------------------------------------------
# ref: https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
#
project = "KubeSpawner"
copyright = f"{datetime.date.today().year}, Project Jupyter Contributors"
author = "Project Jupyter Contributors"
version = "%i.%i" % kubespawner.version_info[:2]
release = kubespawner.__version__


# -- General Sphinx configuration --------------------------------------------
# ref: https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration
#
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.napoleon',
    'sphinxext.rediraffe',
    'autodoc_traits',
    'myst_parser',
]

root_doc = "index"
source_suffix = [".md", ".rst"]

# default_role is set for use with reStructuredText that we still need to use in
# docstrings in the autodoc_traits inspected Python module. It makes single
# backticks around text, like `my_function`, behave as in typical Markdown.
default_role = "literal"


# -- MyST configuration ------------------------------------------------------
# ref: https://myst-parser.readthedocs.io/en/latest/configuration.html
#
myst_enable_extensions = [
    # available extensions: https://myst-parser.readthedocs.io/en/latest/syntax/optional.html
    "colon_fence",
]


# -- Options for HTML output -------------------------------------------------
# ref: https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output
#
html_title = "Kubespawner"
html_theme = "sphinx_book_theme"
html_theme_options = {
    "repository_url": "https://github.com/jupyterhub/kubespawner",
    "use_issues_button": True,
    "use_repository_button": True,
    "use_edit_page_button": True,
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']


# -- Options for intersphinx extension ---------------------------------------
# ref: https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#configuration
#
# The extension makes us able to link like to other projects like below.
#
#     rST  - :external:py:class:`jupyterhub.spawner.Spawner`
#     MyST - {external:py:class}`jupyterhub.spawner.Spawner`
#
# To see what we can link to, do the following where "objects.inv" is appended
# to the sphinx based website:
#
#     python -m sphinx.ext.intersphinx https://jupyterhub.readthedocs.io/en/stable/objects.inv
#
intersphinx_mapping = {
    "jupyterhub": ("https://jupyterhub.readthedocs.io/en/stable/", None),
}

# intersphinx_disabled_reftypes set based on recommendation in
# https://docs.readthedocs.io/en/stable/guides/intersphinx.html#using-intersphinx
intersphinx_disabled_reftypes = ["*"]


# -- Options for linkcheck builder -------------------------------------------
# ref: https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-the-linkcheck-builder
#
linkcheck_ignore = [
    r"(.*)github\.com(.*)#",  # javascript based anchors
    r"(.*)/#%21(.*)/(.*)",  # /#!forum/jupyter - encoded anchor edge case
    r"https://github.com/[^/]*$",  # too many github usernames / searches in changelog
    "https://github.com/jupyterhub/kubespawner/pull/",  # too many pull requests in changelog
    "https://github.com/jupyterhub/kubespawner/compare/",  # too many ref comparisons in changelog
]
linkcheck_anchors_ignore = [
    "/#!",
    "/#%21",
]


# -- Options for the rediraffe extension -------------------------------------
# ref: https://github.com/wpilibsuite/sphinxext-rediraffe#readme
#
# This extensions help us relocated content without breaking links. If a
# document is moved internally, put its path as a dictionary key in the
# redirects dictionary below and its new location in the value.
#
# If the changelog has been moved to live under reference/, then you'd add this
# entry to the rediraffe_redirects dictionary:
#
#   "changelog": "reference/changelog",
#
rediraffe_branch = "main"
rediraffe_redirects = {}
