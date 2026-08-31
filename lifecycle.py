#!/usr/bin/env python3
"""
lifecycle.py — classify vendor part-status strings.

Vendors spell part status inconsistently, and the previous exact-match
set silently dropped every string carrying a parenthetical or a slash.
That failure looked identical to a genuine negative result, which is the
worst possible failure mode for a tool whose whole output is "we found
nothing unusual".

Four classes, not a boolean:

    OBSOLETE  no longer made; authorized channel is finite and draining
    NRND      still made, but not for new designs; channel is intact
    ACTIVE    in production
    UNKNOWN   vendor said nothing we recognise

OBSOLETE and NRND are kept apart deliberately. Zero authorized stock on
an obsolete part means the legitimate channel is exhausted. Zero
authorized stock on an NRND part means something else entirely -- the
part is still being manufactured, so the stock could return next week.
Collapsing them would dilute S-1, the sharpest signal in the system.

Precedence: OBSOLETE > NRND > ACTIVE > UNKNOWN.

A string carrying both an obsolete marker and an NRND marker
("Discontinued - Not Recommended for New Designs") is obsolete: the
stronger claim wins. A string carrying only an NRND marker alongside a
last-time-buy notice ("NRND / Last Time Buy") is NRND, because a last
time buy means the authorized channel is still open.

Run this file to execute its regression tests:

    python3 lifecycle.py
"""

import re

OBSOLETE = "OBSOLETE"
NRND = "NRND"
ACTIVE = "ACTIVE"
UNKNOWN = "UNKNOWN"

# Word-boundary anchored so "eol" does not match inside another word and
# "active" does not match inside "inactive".
_OBSOLETE_RE = re.compile(r"""
      \bobsolete\b
    | \bdiscontinued\b
    | \beol\b
    | \bend [\s\-_]* of [\s\-_]* life\b
    | \bend [\s\-_]* of [\s\-_]* production\b
    | \bno \s+ longer \s+ (manufactured|available|produced)\b
    | \bnot \s+ manufactured\b
    | \binactive\b
""", re.IGNORECASE | re.VERBOSE)

_NRND_RE = re.compile(r"""
      \bnrnd\b
    | \bnot \s+ recommended\b
    | \bnot \s+ for \s+ new \s+ design
    | \blast [\s\-_]* time [\s\-_]* buy\b
    | \bltb\b
""", re.IGNORECASE | re.VERBOSE)

_ACTIVE_RE = re.compile(r"""
      \bactive\b
    | \bproduction\b
    | \bnew \s+ product\b
    | \bpreliminary\b
""", re.IGNORECASE | re.VERBOSE)


def classify(raw) -> str:
    """Map a raw vendor lifecycle string to one of the four classes."""
    text = (raw or "").strip()
    if not text:
        return UNKNOWN
    if _OBSOLETE_RE.search(text):
        return OBSOLETE
    if _NRND_RE.search(text):
        return NRND
    if _ACTIVE_RE.search(text):
        return ACTIVE
    return UNKNOWN


def is_obsolete(raw) -> bool:
    return classify(raw) == OBSOLETE


def lifecycle_from_specs(specs) -> str:
    """Pull the raw lifecycle string out of a Nexar spec bag.

    The attribute key name varies by manufacturer, so match loosely and
    return the raw value untouched -- classification happens separately
    so the original string stays in the CSV for auditing.
    """
    for s in specs or []:
        name = ((s.get("attribute") or {}).get("shortname") or "").lower()
        if "lifecycle" in name or name in {"status", "partstatus",
                                           "part_status", "productstatus"}:
            return s.get("displayValue") or ""
    return ""


# ----------------------------------------------------------------------
# Regression tests. Real strings observed across vendor catalogues.
# ----------------------------------------------------------------------

_CASES = [
    # obsolete -- including the parenthetical and slash forms that the
    # previous exact-match implementation silently dropped
    ("Obsolete",                                  OBSOLETE),
    ("Obsolete (End of Life)",                    OBSOLETE),
    ("EOL / Discontinued",                        OBSOLETE),
    ("No Longer Manufactured",                    OBSOLETE),
    ("Discontinued",                              OBSOLETE),
    ("End of Life",                               OBSOLETE),
    ("End-of-Life",                               OBSOLETE),
    ("EOL",                                       OBSOLETE),
    ("Inactive",                                  OBSOLETE),
    ("Discontinued at Digi-Key",                  OBSOLETE),
    ("Obsolete / Discontinued",                   OBSOLETE),
    # obsolete wins over NRND when a string carries both
    ("Discontinued - Not Recommended for New Designs", OBSOLETE),

    # nrnd -- still manufactured, so not an S-1 candidate
    ("NRND",                                      NRND),
    ("Not Recommended for New Designs",           NRND),
    ("NRND / Last Time Buy",                      NRND),
    ("Last Time Buy",                             NRND),
    ("Not For New Designs",                       NRND),

    # active
    ("Active",                                    ACTIVE),
    ("Production",                                ACTIVE),
    ("In Production",                             ACTIVE),
    ("New Product",                               ACTIVE),
    ("Preliminary",                               ACTIVE),

    # unknown
    ("",                                          UNKNOWN),
    (None,                                        UNKNOWN),
    ("Contact Manufacturer",                      UNKNOWN),
]


def _run_tests() -> int:
    failed = 0
    for raw, expected in _CASES:
        got = classify(raw)
        if got != expected:
            failed += 1
            print(f"  FAIL  {raw!r:<52} expected {expected}, got {got}")
    # "active" must not match inside "inactive"
    assert classify("Inactive") == OBSOLETE, "inactive misclassified as active"
    print(f"{len(_CASES) - failed}/{len(_CASES)} lifecycle assertions passed")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run_tests() else 0)
