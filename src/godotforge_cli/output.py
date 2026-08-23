"""Output bridge: hand the envelope to the core serializer and print it."""

from __future__ import annotations

from godotforge_core.output import Envelope, OutputFormat, serialize


def emit(envelope: Envelope, fmt: OutputFormat) -> None:
    import sys

    sys.stdout.write(serialize(envelope, fmt) + "\n")
