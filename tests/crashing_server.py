"""Server that dies on startup, leaving its reason on stderr.

Exists to prove the probe surfaces exit code + stderr tail as evidence
instead of reporting a bare timeout.
"""

import sys

print("boom: fatal config error — MISSING_API_KEY is not set", file=sys.stderr)
sys.exit(1)
