from __future__ import annotations

__all__ = ["UsageError"]

try:
    from typer._click.exceptions import UsageError
except ImportError:  # Typer before its vendored command runtime.
    from click.exceptions import UsageError  # type: ignore[assignment]
