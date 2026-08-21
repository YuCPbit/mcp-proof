"""Failure taxonomy shared across the CLI commands.

Every command maps outcomes onto the same exit codes: 0 = audit completed and
the target passed; 1 = audit completed and the target failed it; 2 = the
audit itself did not complete — and a 2 is never evidence against the target.
These exceptions are the "did not complete" half: the dispatch boundary in
runner.py converts each into a stable one-line message and exit code 2.
"""


class BaselineMissingError(RuntimeError):
    """A fixtures directory was given but holds no recorded baseline."""


class FixtureIntegrityError(RuntimeError):
    """The fixture set failed integrity verification; nothing was replayed.

    A baseline that cannot be verified (tampered, incomplete, or predating
    contract hashing) must not gate anything: drift measured against it would
    blame the target for the baseline's problems.
    """

    def __init__(self, problems: list):
        self.problems = list(problems)
        lines = [f"[{p.kind}] {p.tool} ({p.fixture}): {p.detail}" for p in self.problems]
        super().__init__(
            "fixture-set integrity verification failed, nothing was replayed:\n  "
            + "\n  ".join(lines)
        )


class UnsupportedReportSchema(ValueError):
    """A report model declares a schema newer than this mcp-proof understands."""
