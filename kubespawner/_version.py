# __version__ should be updated using tbump, based on configuration in
# pyproject.toml, according to instructions in RELEASE.md.
#
__version__ = "7.0.0"

# version_info looks like (1, 2, 3, "dev") if __version__ is 1.2.3.dev
version_info = tuple(int(p) if p.isdigit() else p for p in __version__.split("."))
