"""Root conftest to put the repository root on sys.path.

This makes ``custom_components.switch2`` importable in CI, where the
package itself is not pip-installed.
"""
