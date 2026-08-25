"""Stable, Forge-owned exit codes.

The CLI converts these into process exit codes. Deep service code never calls
``sys.exit``; it returns a result object carrying one of these codes.
"""

from enum import IntEnum


class ForgeExitCode(IntEnum):
    """ForgeExitCode — production class."""
    SUCCESS = 0
    VALIDATION_FAILURE = 1
    CONFIGURATION_FAILURE = 2
    TOOL_UNAVAILABLE = 3
    PATCH_CONFLICT = 4
    INTERNAL_FAILURE = 5


EXIT_CODE_MESSAGES = {
    ForgeExitCode.SUCCESS: "success",
    ForgeExitCode.VALIDATION_FAILURE: "validation failure",
    ForgeExitCode.CONFIGURATION_FAILURE: "configuration failure",
    ForgeExitCode.TOOL_UNAVAILABLE: "external tool unavailable",
    ForgeExitCode.PATCH_CONFLICT: "patch conflict",
    ForgeExitCode.INTERNAL_FAILURE: "internal failure",
}
