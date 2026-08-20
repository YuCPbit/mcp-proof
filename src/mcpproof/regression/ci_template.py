"""Leave-behind CI: a GitHub Actions workflow that replays the fixture suite."""

import shlex

_TEMPLATE = """\
# The recorded fixtures in {fixtures_raw} are the behavioral contract: any drift fails this job.
name: mcp-proof regression gate
on:
  push:
  pull_request:
jobs:
  replay:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install mcp-proof
        run: pip install git+https://github.com/YuCPbit/mcp-proof
      - name: Replay golden fixtures against the live server
        run: mcp-proof replay --fixtures {fixtures} {target}
"""


def github_action_yaml(
    server_cmd: list[str] | None, fixtures_dir: str, url: str | None = None
) -> str:
    if url:
        target = f"--url {shlex.quote(url)}"
    else:
        target = f"-- {shlex.join(server_cmd)}"
    return _TEMPLATE.format(
        target=target,
        fixtures=shlex.quote(fixtures_dir),
        fixtures_raw=fixtures_dir,
    )
