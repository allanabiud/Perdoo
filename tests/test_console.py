"""Theme styles referenced by CLI output must exist."""

import pytest

from perdoo.console import CONSOLE


@pytest.mark.parametrize(
    "style",
    [
        "success",
        "logging.level.debug",
        "logging.level.info",
        "logging.level.warning",
        "logging.level.error",
        "logging.level.critical",
    ],
)
def test_console_accepts_styles_used_by_cli_output(style: str) -> None:
    """`CONSOLE.print(..., style=...)` raises MissingStyle for undefined styles.

    The local sync path prints its success line with style="success"; when that
    style was missing from the theme every sync failed with
    "Failed to get style 'success'".
    """
    with CONSOLE.capture() as capture:
        CONSOLE.print("message", style=style)
    assert "message" in capture.get()
