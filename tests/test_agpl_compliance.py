"""AGPL §13 compliance gates — WR-06.

The README + UI footer + Dockerfile copy of ``web/index.html`` contain a literal
``<OWNER>`` placeholder that an operator MUST substitute before a public deploy.
A documentation note is not the same as an enforceable gate, so this module turns
the requirement into a code-level guard.

Two assertions per file:

  1. The pristine repo state DOES carry the placeholder (catches the case where
     someone accidentally hand-substituted a bogus value during development,
     baking it into git history).
  2. A separate "deploy gate" test (opt-in via ``LOGOSWAP_RELEASE_GATE=1``) FAILS
     when the placeholder is still present — used by the deploy pipeline to
     fail-closed if the substitution step was skipped.

Why split into two modes: dev branches must stay green (placeholder is the
intended pristine state) but the release pipeline must fail loud when the
operator forgets to substitute. The opt-in env var keeps the two regimes
unambiguous (CI default = pristine assertion; deploy = substitution-check).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PLACEHOLDER = "<OWNER>"
_FILES_WITH_PLACEHOLDER = (
    _REPO_ROOT / "web" / "index.html",
    _REPO_ROOT / "README.md",
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", _FILES_WITH_PLACEHOLDER, ids=lambda p: p.name)
def test_owner_placeholder_present_in_pristine_repo(path):
    """Pristine-state guard: ensure the placeholder is in the source tree.

    A dev who accidentally hand-substitutes their personal GitHub handle into
    web/index.html or README.md and commits it would silently lock the AGPL
    disclosure URL to that handle for every subsequent deploy. Catch that here.
    """
    assert path.is_file(), f"expected {path} to exist"
    body = _read_text(path)
    assert _PLACEHOLDER in body, (
        f"{path.name} no longer contains the '{_PLACEHOLDER}' placeholder — if you "
        "actually want to bake the GitHub owner into the repo, update this test; "
        "otherwise revert the hand-substitution and let the deploy pipeline replace it."
    )


@pytest.mark.skipif(
    os.environ.get("LOGOSWAP_RELEASE_GATE", "") != "1",
    reason=(
        "Release-only gate: set LOGOSWAP_RELEASE_GATE=1 in the deploy pipeline "
        "AFTER substituting <OWNER> with the real public GitHub owner. The dev "
        "default (env unset) skips this so feature branches stay green."
    ),
)
@pytest.mark.parametrize("path", _FILES_WITH_PLACEHOLDER, ids=lambda p: p.name)
def test_owner_placeholder_substituted_before_release(path):
    """Release-gate: fail-closed if the operator forgot to substitute <OWNER>.

    Wire this into the deploy pipeline:

        LOGOSWAP_RELEASE_GATE=1 pytest tests/test_agpl_compliance.py

    If the substitution step (sed -i / Dockerfile build-arg / manual edit) was
    skipped, this turns a silent broken link in the AGPL §13 disclosure into a
    loud build failure — the exact compliance contract WR-06 calls for.
    """
    body = _read_text(path)
    assert _PLACEHOLDER not in body, (
        f"{path.name} still contains the '{_PLACEHOLDER}' placeholder — substitute it "
        "with the real public GitHub repo owner before deploying. AGPL §13 requires the "
        "running UI's footer link to resolve to the actual source repository."
    )
