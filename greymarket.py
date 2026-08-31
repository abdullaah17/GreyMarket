#!/usr/bin/env python3
"""
greymarket.py — counterfeit risk signals from public part listings.

Core signal:
    A part is obsolete. Authorized distributors have no stock.
    An unauthorized broker claims thousands of units.
    Where did those units come from?

Commands:
    discover   find obsolete parts in a category -> parts.csv
    scan       pull every seller offer, score, -> listings.csv

Usage:
    python greymarket.py discover --category "microcontroller" --limit 200
    python greymarket.py scan --parts parts.csv

    python greymarket.py scan --demo        # no API key needed

Credentials:
    export NEXAR_CLIENT_ID=...
    export NEXAR_CLIENT_SECRET=...
"""

import argparse
import csv
import os
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

import requests

from lifecycle import (ACTIVE, NRND, OBSOLETE, UNKNOWN,
                       classify, lifecycle_from_specs)

TOKEN_URL = "https://identity.nexar.com/connect/token"
API_URL = "https://api.nexar.com/graphql"

BROKER_QTY_SUSPICIOUS = 1000
AUTH_STOCK_MULTIPLE = 10
PRICE_RATIO_SUSPICIOUS = 0.5

# S-2 needs an absolute floor as well as a multiple. Authorized stock on
# an obsolete part dwindles by definition, so the multiple alone is
# near-worthless: a distributor down to 3 units plus any broker holding
# 31 trips a 10x threshold, and that is an obsolete part behaving exactly
# as expected. The ratio only carries information once the absolute
# number is non-trivial. 100 is arbitrary and untuned.
S2_MIN_QTY = 100

# Quantity tier at which prices are compared. Sellers publish different
# numbers of price breaks -- authorized distributors typically publish
# many, brokers typically one -- so taking each seller's cheapest break
# compares a broker's single-unit price against a distributor's
# 10,000-unit price. That drags the median down and suppresses exactly
# the underpricing we are looking for. Compare everyone at one tier.
REFERENCE_QTY = 1

# S-4. Share of the scanned obsolete parts that one unauthorized seller
# claims stock of. Arbitrary and untuned -- see the caveat in report().
CATALOGUE_SHARE_SUSPICIOUS = 0.30
MIN_OBSOLETE_SAMPLE = 20


# ----------------------------------------------------------------------

@dataclass
class Offer:
    mpn: str
    manufacturer: str
    lifecycle: str
    seller: str
    authorized: bool
    quantity: int
    unit_price: float
    currency: str = "USD"
    price_qty: int = 1
    price_break_count: int = 0
    retrieved_at: str = ""
    # filled in during scoring
    lifecycle_class: str = UNKNOWN
    authorized_stock: int = 0
    broker_stock: int = 0
    median_price: float | None = None
    price_ratio: float | None = None
    seller_obsolete_share: float | None = None
    flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.lifecycle_class = classify(self.lifecycle)

    @property
    def score(self) -> int:
        return len(self.flags)

    @property
    def is_obsolete(self) -> bool:
        return self.lifecycle_class == OBSOLETE

    @property
    def is_nrnd(self) -> bool:
        return self.lifecycle_class == NRND


CSV_FIELDS = [
    "mpn", "manufacturer", "lifecycle", "lifecycle_class",
    "seller", "authorized", "quantity", "unit_price", "currency",
    "price_qty", "price_break_count", "retrieved_at",
    "authorized_stock", "broker_stock", "median_price", "price_ratio",
    "seller_obsolete_share", "flags",
]


# ----------------------------------------------------------------------
# API
# ----------------------------------------------------------------------

DISCOVER_QUERY = """
query Discover($q: String!, $limit: Int!, $start: Int!) {
  supSearch(q: $q, limit: $limit, start: $start) {
    hits
    results {
      part {
        mpn
        manufacturer { name }
        category { name }
        specs { attribute { shortname } displayValue }
      }
    }
  }
}
"""

OFFERS_QUERY = """
query Offers($mpn: String!) {
  supSearchMpn(q: $mpn, limit: 1) {
    results {
      part {
        mpn
        manufacturer { name }
        specs { attribute { shortname } displayValue }
        sellers {
          company { name }
          isAuthorized
          offers {
            inventoryLevel
            prices { price currency quantity }
          }
        }
      }
    }
  }
}
"""


def get_token(cid: str, secret: str) -> str:
    r = requests.post(TOKEN_URL, timeout=30, data={
        "grant_type": "client_credentials",
        "client_id": cid, "client_secret": secret})
    r.raise_for_status()
    return r.json()["access_token"]


def gql(token: str, query: str, variables: dict) -> dict:
    r = requests.post(API_URL, timeout=40,
                      json={"query": query, "variables": variables},
                      headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    payload = r.json()
    if "errors" in payload:
        msg = payload["errors"][0].get("message", "unknown")
        raise RuntimeError(f"API error: {msg}")
    return payload.get("data") or {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------------
# discover
# ----------------------------------------------------------------------

def discover(token: str, category: str, limit: int, out: str) -> None:
    """Walk a category, keep the parts that are obsolete or NRND.

    NRND parts are collected but classified separately -- they are still
    in production, so they are not S-1 candidates.
    """
    found, start, page = [], 0, 100
    seen_raw: Counter = Counter()
    seen_class: Counter = Counter()

    while len(found) < limit and start < 1000:
        data = gql(token, DISCOVER_QUERY,
                   {"q": category, "limit": page, "start": start})
        results = (data.get("supSearch") or {}).get("results") or []
        if not results:
            break
        for r in results:
            part = r["part"]
            lc = lifecycle_from_specs(part.get("specs"))
            klass = classify(lc)
            seen_raw[lc.strip() or "<empty>"] += 1
            seen_class[klass] += 1
            if klass in (OBSOLETE, NRND):
                found.append({
                    "mpn": part["mpn"],
                    "manufacturer": (part.get("manufacturer") or {}).get("name", ""),
                    "category": (part.get("category") or {}).get("name", ""),
                    "lifecycle": lc,
                    "lifecycle_class": klass,
                })
        start += page
        print(f"  scanned {start}, kept {len(found)}")
        time.sleep(0.4)

    found = found[:limit]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["mpn", "manufacturer", "category",
                                          "lifecycle", "lifecycle_class"])
        w.writeheader()
        w.writerows(found)

    n_obs = sum(1 for r in found if r["lifecycle_class"] == OBSOLETE)
    print(f"\n{len(found)} parts -> {out}  "
          f"({n_obs} obsolete, {len(found) - n_obs} NRND)")

    # Always report the classification split of everything scanned, not
    # just the kept rows. A low-but-non-zero count is the misleading
    # outcome: it reads as success while most parts silently classify as
    # UNKNOWN, and it quietly shrinks S-4's denominator, which counts
    # only parts that classified as OBSOLETE.
    scanned = sum(seen_class.values())
    if not scanned:
        print("\nNo parts returned at all. Nothing to classify.")
        return

    print(f"\nclassification of all {scanned} parts scanned:")
    for k in (OBSOLETE, NRND, ACTIVE, UNKNOWN):
        n = seen_class.get(k, 0)
        print(f"    {k:<9} {n:>6}  {n / scanned:>6.1%}")

    unknown_share = seen_class.get(UNKNOWN, 0) / scanned
    if unknown_share < 0.30:
        return

    # UNKNOWN dominates. Two different problems with two different fixes,
    # separated by whether the vendor gave us a string at all.
    empty = seen_raw.get("<empty>", 0)
    unknown_total = seen_class.get(UNKNOWN, 0)
    empty_share = empty / unknown_total if unknown_total else 0

    print(f"\n  WARNING: {unknown_share:.0%} of parts scanned classified "
          f"as UNKNOWN.")
    print("  Do not read the counts above as a result until this is "
          "resolved.")
    print("\n  raw lifecycle values seen, most common first:")
    for value, count in seen_raw.most_common(15):
        print(f"    {count:>5}  {value!r}  -> {classify(value)}")

    if empty_share >= 0.5:
        print(f"\n  {empty_share:.0%} of the UNKNOWN parts carried no "
              f"lifecycle string at all.")
        print("  The field is sparse or absent on these sources, not "
              "misspelled. A")
        print("  corrected attribute key will not fix it -- lifecycle "
              "needs a fallback")
        print("  source. Check whether the key is present on some "
              "manufacturers only.")
    else:
        print("\n  The values above are populated but unrecognised: a "
              "vocabulary gap.")
        print("  Add them to lifecycle.py and re-run its tests "
              "(python3 lifecycle.py).")


# ----------------------------------------------------------------------
# scan
# ----------------------------------------------------------------------

def pick_price_break(prices: list) -> dict | None:
    """Choose the break nearest REFERENCE_QTY so sellers compare fairly.

    Ties resolve to the lower quantity.
    """
    valid = [p for p in prices if p.get("price") is not None]
    if not valid:
        return None

    def key(p):
        q = int(p.get("quantity") or 1)
        return (abs(q - REFERENCE_QTY), q)

    return min(valid, key=key)


def fetch_offers(token: str, mpn: str) -> list[Offer]:
    # One timestamp per part fetch, so every row from a single part
    # carries an identical retrieval time and a run stays internally
    # consistent when it is compared against a later snapshot.
    retrieved_at = now_iso()

    data = gql(token, OFFERS_QUERY, {"mpn": mpn})
    results = (data.get("supSearchMpn") or {}).get("results") or []
    if not results:
        return []
    part = results[0]["part"]
    mfr = (part.get("manufacturer") or {}).get("name", "")
    lc = lifecycle_from_specs(part.get("specs"))

    out = []
    for seller in part.get("sellers") or []:
        name = (seller.get("company") or {}).get("name", "unknown")
        auth = bool(seller.get("isAuthorized"))
        for offer in seller.get("offers") or []:
            prices = offer.get("prices") or []
            best = pick_price_break(prices)
            if best is None:
                continue
            out.append(Offer(
                mpn=part.get("mpn", mpn), manufacturer=mfr, lifecycle=lc,
                seller=name, authorized=auth,
                quantity=int(offer.get("inventoryLevel") or 0),
                unit_price=float(best.get("price") or 0),
                currency=best.get("currency") or "USD",
                price_qty=int(best.get("quantity") or 1),
                price_break_count=len(prices),
                retrieved_at=retrieved_at))
    return out


def score(offers: list[Offer]) -> None:
    """The whole thesis lives in this function."""
    by_mpn: dict[str, list[Offer]] = {}
    for o in offers:
        by_mpn.setdefault(o.mpn.upper(), []).append(o)

    for group in by_mpn.values():
        auth_stock = sum(o.quantity for o in group if o.authorized)
        broker_stock = sum(o.quantity for o in group if not o.authorized)
        prices = [o.unit_price for o in group if o.unit_price > 0]
        median = statistics.median(prices) if prices else None

        for o in group:
            o.authorized_stock = auth_stock
            o.broker_stock = broker_stock
            if median:
                o.median_price = round(median, 4)
                o.price_ratio = round(o.unit_price / median, 3)

            # S-1..S-3 fire on OBSOLETE only. An NRND part is still in
            # production, so an empty authorized channel means something
            # different and must not be counted as the same signal.
            if o.authorized or not o.is_obsolete:
                continue

            # the core signal: nobody legitimate has it, this guy has piles
            if auth_stock == 0 and o.quantity >= BROKER_QTY_SUSPICIOUS:
                o.flags.append("phantom_stock")

            # broker holds more than the entire authorized channel, and
            # holds enough of it for the comparison to mean anything
            if (auth_stock > 0
                    and o.quantity > auth_stock * AUTH_STOCK_MULTIPLE
                    and o.quantity >= S2_MIN_QTY):
                o.flags.append("outstocks_channel")

            # obsolete parts get more expensive, not cheaper
            if (o.price_ratio is not None
                    and o.price_ratio <= PRICE_RATIO_SUSPICIOUS):
                o.flags.append("underpriced")

    score_catalogue(offers, by_mpn)


def score_catalogue(offers: list[Offer], by_mpn: dict) -> None:
    """S-4 catalogue_implausibility, aggregated across the whole run.

    A broker holding genuine surplus holds a narrow range. A seller
    claiming stock across a large share of every obsolete part scanned
    is either a pure intermediary or worse.
    """
    obsolete_mpns = {m for m, g in by_mpn.items()
                     if any(o.is_obsolete for o in g)}
    n = len(obsolete_mpns)
    if n < MIN_OBSOLETE_SAMPLE:
        return

    seller_parts: dict[str, set] = {}
    for o in offers:
        if o.authorized or not o.is_obsolete or o.quantity <= 0:
            continue
        seller_parts.setdefault(o.seller, set()).add(o.mpn.upper())

    for o in offers:
        if o.authorized or not o.is_obsolete:
            continue
        share = len(seller_parts.get(o.seller, ())) / n
        o.seller_obsolete_share = round(share, 3)
        if share >= CATALOGUE_SHARE_SUSPICIOUS:
            o.flags.append("catalogue_implausibility")


def _mean(xs) -> float | None:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def report(offers: list[Offer], demo: bool = False) -> None:
    parts = {o.mpn.upper() for o in offers}
    classes = Counter(o.lifecycle_class for o in offers)
    obsolete_parts = {o.mpn.upper() for o in offers if o.is_obsolete}
    phantom = [o for o in offers if "phantom_stock" in o.flags]
    catalogue = [o for o in offers if "catalogue_implausibility" in o.flags]
    flagged = [o for o in offers if o.flags]

    print("\n" + "=" * 66)
    print("RESULT")
    print("=" * 66)
    print(f"  parts              {len(parts)}  ({len(obsolete_parts)} obsolete)")
    print(f"  offers             {len(offers)}")
    print(f"  by lifecycle       " + ", ".join(
        f"{k} {classes.get(k, 0)}" for k in (OBSOLETE, NRND, ACTIVE, UNKNOWN)))
    print(f"  flagged            {len(flagged)}")
    print(f"  phantom stock      {len(phantom)}")

    # Price-break asymmetry. This is the bias that made the old
    # cheapest-break selection suppress `underpriced`.
    auth_breaks = _mean(o.price_break_count for o in offers
                        if o.authorized and o.price_break_count)
    brok_breaks = _mean(o.price_break_count for o in offers
                        if not o.authorized and o.price_break_count)
    if auth_breaks and brok_breaks:
        print(f"\n  price breaks       authorized {auth_breaks:.1f}"
              f"   broker {brok_breaks:.1f}   "
              f"(compared at qty {REFERENCE_QTY})")
        if demo:
            print("    NOTE: synthetic. The demo generator sets these counts,")
            print("    so this gap is an assumption being displayed back, not")
            print("    a measurement. Check it against live data before")
            print("    tuning S-3.")

    if phantom:
        print("\n  obsolete, zero authorized stock, broker claims piles:\n")
        for o in sorted(phantom, key=lambda x: -x.quantity)[:12]:
            ratio = f"{o.price_ratio:.2f}x" if o.price_ratio else "-"
            print(f"    {o.mpn:<18} {o.seller:<24} "
                  f"{o.quantity:>7} units   {ratio:>7} median")

    # NRND is reported, never flagged. Zero authorized stock on a part
    # that is still being manufactured is interesting for a different
    # reason: the channel could refill next week.
    nrnd_empty = [o for o in offers
                  if o.is_nrnd and not o.authorized
                  and o.authorized_stock == 0
                  and o.quantity >= BROKER_QTY_SUSPICIOUS]
    if nrnd_empty:
        print(f"\n  NRND, zero authorized stock, broker piles: "
              f"{len(nrnd_empty)} offers")
        print("    Separate observation, not S-1. These parts are still in")
        print("    production, so an empty channel is not exhaustion.")

    if catalogue:
        sellers = sorted({(o.seller, o.seller_obsolete_share)
                          for o in catalogue}, key=lambda t: -t[1])
        print(f"\n  broad obsolete catalogues "
              f"(>= {CATALOGUE_SHARE_SUSPICIOUS:.0%} of "
              f"{len(obsolete_parts)} obsolete parts scanned):\n")
        for name, share in sellers[:10]:
            print(f"    {name:<28} {share:>6.0%}")
        print("\n    Suggestive, not damning. Two confounds:")
        print("    - Sample-dependent. Scan 200 microcontrollers and a")
        print("      microcontroller specialist looks broad legitimately.")
        print("    - Cannot separate a large independent distributor from")
        print("      a seller listing stock they do not hold.")
    elif len(obsolete_parts) < MIN_OBSOLETE_SAMPLE:
        print(f"\n  S-4 skipped: {len(obsolete_parts)} obsolete parts, "
              f"needs {MIN_OBSOLETE_SAMPLE}.")

    print("\n  VERDICT")
    if len(phantom) >= 20:
        print("    Strong. The anomaly is real and common.")
        print("    Now go show these rows to a buyer.")
    elif len(phantom) >= 5:
        print("    Present but thin. Widen the part list.")
    elif classes.get(OBSOLETE, 0) == 0:
        print("    No obsolete parts classified. Before concluding anything,")
        print("    check the lifecycle strings -- run: python3 lifecycle.py")
    else:
        print("    No signal. Lifecycle parsing produced obsolete parts, so")
        print("    the absence is real for this sample. Widen it.")
    print()


# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# demo
#
# The generator used to roll everything at random, which left
# outstocks_channel structurally unreachable: the only offers large
# enough to trip the multiple were the ones where the authorized channel
# had been zeroed, and S-2 requires authorized_stock > 0. Nobody noticed
# because nothing checked that each signal ever executed.
#
# Explicit scenarios instead. Random rolls cannot guarantee coverage; a
# table can. Three of these are negative controls that must stay clean.
# ----------------------------------------------------------------------

AUTH_NAMES = ["Digi-Key", "Mouser", "Arrow"]

BROKERS = ["Apex Components", "Zenith Electronics", "Sunrise Semi",
           "Meridian Supply", "Northgate Electronics", "Harbor Point Supply",
           "Vantage Components", "Redstone Parts", "Kestrel Semiconductor",
           "Lattice Trading", "Orion Component Group", "Bluefin Electronics"]

# Appears across half the obsolete parts, so it is the only seller that
# should trip S-4. Its quantities are capped below S2_MIN_QTY and its
# prices held above the median deliberately: if it could also trip S-1,
# S-2 or S-3 it would contaminate every scenario it touches, including
# the negative controls, and per-scenario reasoning would be worthless.
WIDE_SELLER = "Global Parts Exchange"
WIDE_QTY = (20, 90)
WIDE_PRICE = (1.0, 1.6)

# Part-level signals. S-4 is a seller-level property and is expected to
# appear anywhere the wide seller does, controls included, so it is
# excluded from the per-scenario assertions.
PART_SIGNALS = ("phantom_stock", "outstocks_channel", "underpriced")
ALL_SIGNALS = PART_SIGNALS + ("catalogue_implausibility",)


@dataclass
class Scenario:
    code: str
    parts: int
    lifecycle: str
    auth_qty: tuple      # per authorized seller; (0, 0) = exhausted channel
    broker_qty: tuple
    broker_price: tuple  # multiple of the part's base price
    expect: tuple        # part-level signals this scenario must produce
    note: str = ""


DEMO_SCENARIOS = [
    Scenario("PHANTOM", 6, "Obsolete (End of Life)", (0, 0),
             (2000, 9000), (0.20, 0.45),
             ("phantom_stock", "underpriced"),
             "the core case: channel exhausted, broker piles, cheap"),

    Scenario("PHANTOMFP", 3, "Obsolete", (0, 0),
             (1500, 4000), (1.5, 2.5),
             ("phantom_stock",),
             "phantom stock priced as scarcity predicts; S-3 must not fire"),

    Scenario("OUTSTOCK", 4, "EOL / Discontinued", (20, 40),
             (1200, 3000), (1.2, 2.0),
             ("outstocks_channel",),
             "residual channel, broker clears both multiple and floor"),

    Scenario("DWINDLE", 4, "No Longer Manufactured", (1, 3),
             (65, 95), (1.2, 2.0),
             (),
             "CONTROL: clears the 10x multiple, sits below S2_MIN_QTY. "
             "An obsolete part behaving normally. Must stay clean."),

    Scenario("UNDERPX", 4, "Obsolete", (500, 900),
             (10, 60), (0.15, 0.30),
             ("underpriced",),
             "healthy channel, small cheap broker lot; S-3 in isolation"),

    Scenario("CLEAN", 5, "Obsolete", (400, 900),
             (20, 300), (1.2, 3.0),
             (),
             "CONTROL: obsolete and entirely unremarkable"),

    Scenario("NRNDSTARVE", 4, "NRND / Last Time Buy", (0, 0),
             (3000, 8000), (0.20, 0.45),
             (),
             "CONTROL: exhausted channel on an in-production part. "
             "Shaped exactly like PHANTOM. Must fire nothing."),

    Scenario("NRNDOK", 2, "NRND", (200, 600),
             (20, 200), (1.2, 2.0),
             (),
             "ordinary NRND part"),

    Scenario("ACTIVE", 3, "Active", (300, 900),
             (20, 400), (1.2, 2.5),
             (),
             "in production; nothing here is a signal"),
]


def demo_offers() -> list[Offer]:
    """Synthetic data. Proves the pipeline runs; proves nothing else.

    Every rate and range in this table was chosen by hand, including the
    price-break gap between authorized sellers and brokers.
    """
    rng = random.Random(7)
    ts = now_iso()
    out: list[Offer] = []
    broker_cursor = 0
    obsolete_seen = 0

    for sc in DEMO_SCENARIOS:
        for i in range(1, sc.parts + 1):
            mpn = f"{sc.code}-{i:02d}"
            base = rng.uniform(3, 60)

            for d in rng.sample(AUTH_NAMES, 2):
                out.append(Offer(
                    mpn, "DemoCorp", sc.lifecycle, d, True,
                    rng.randint(*sc.auth_qty) if sc.auth_qty[1] else 0,
                    round(base * rng.uniform(0.95, 1.10), 4),
                    price_qty=1, price_break_count=rng.randint(4, 7),
                    retrieved_at=ts))

            # Round-robin rather than sampling, so no ordinary broker
            # drifts above the S-4 share threshold by chance.
            for _ in range(2):
                name = BROKERS[broker_cursor % len(BROKERS)]
                broker_cursor += 1
                out.append(Offer(
                    mpn, "DemoCorp", sc.lifecycle, name, False,
                    rng.randint(*sc.broker_qty),
                    round(base * rng.uniform(*sc.broker_price), 4),
                    price_qty=1, price_break_count=rng.randint(1, 2),
                    retrieved_at=ts))

            if classify(sc.lifecycle) == OBSOLETE:
                obsolete_seen += 1
                if obsolete_seen % 2 == 0:
                    out.append(Offer(
                        mpn, "DemoCorp", sc.lifecycle, WIDE_SELLER, False,
                        rng.randint(*WIDE_QTY),
                        round(base * rng.uniform(*WIDE_PRICE), 4),
                        price_qty=1, price_break_count=1,
                        retrieved_at=ts))
    return out


def demo_selfcheck(offers: list[Offer]) -> int:
    """Assert every signal executed and the negative controls stayed clean.

    The dead S-2 branch survived because nothing ever checked that a
    signal fired. This is the general fix, not a patch for that one bug.
    """
    by_code: dict[str, list[Offer]] = {}
    for o in offers:
        by_code.setdefault(o.mpn.split("-")[0], []).append(o)
    counts = Counter(f for o in offers for f in o.flags)

    print("\n  DEMO COVERAGE")
    failures = 0
    for sig in ALL_SIGNALS:
        n = counts.get(sig, 0)
        if n == 0:
            failures += 1
            print(f"    {sig:<28} {n:>5}   <-- NEVER FIRES")
        else:
            print(f"    {sig:<28} {n:>5}")

    print("\n  SCENARIO ASSERTIONS")
    for sc in DEMO_SCENARIOS:
        rows = by_code.get(sc.code, [])
        got = {f for o in rows for f in o.flags if f in PART_SIGNALS}
        want = set(sc.expect)
        control = "CONTROL " if not want else ""
        if got == want:
            shown = ", ".join(sorted(want)) or "clean"
            print(f"    ok    {control}{sc.code:<12} {shown}")
        else:
            failures += 1
            print(f"    FAIL  {control}{sc.code:<12} "
                  f"expected {sorted(want) or ['clean']}, "
                  f"got {sorted(got) or ['clean']}")

    print()
    if failures:
        print(f"  {failures} coverage failure(s). The demo is not "
              f"exercising the scoring logic as intended.\n")
    else:
        print("  All signals executed; negative controls clean.\n")
    return failures


def write_csv(offers: list[Offer], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for o in sorted(offers, key=lambda x: (-x.score, -x.quantity)):
            d = asdict(o)
            d["flags"] = "|".join(o.flags)
            w.writerow(d)


def auth_or_die() -> str:
    cid, sec = os.getenv("NEXAR_CLIENT_ID"), os.getenv("NEXAR_CLIENT_SECRET")
    if not (cid and sec):
        sys.exit("Set NEXAR_CLIENT_ID and NEXAR_CLIENT_SECRET (or use --demo)")
    try:
        return get_token(cid, sec)
    except requests.RequestException as e:
        sys.exit(f"Could not obtain a token: {e}\n"
                 f"Check NEXAR_CLIENT_ID and NEXAR_CLIENT_SECRET.")


def die_on_api_error(e: Exception) -> None:
    """Turn an API refusal into something readable.

    discover has no per-part error tolerance the way scan does -- one
    bad response ends the run -- and it is the step most likely to meet
    a quota or entitlement problem, so the message has to say which.
    """
    msg = str(e)
    print(f"\nAPI refused the request: {msg}", file=sys.stderr)
    if "limit" in msg.lower() or "plan" in msg.lower():
        print("\nThis is an account entitlement problem, not a code or "
              "credential problem.\nThe token was issued; the plan has no "
              "part quota. Add the Supply API\nto the app in the Nexar "
              "portal, or contact api@nexar.com.", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover")
    d.add_argument("--category", required=True)
    d.add_argument("--limit", type=int, default=200)
    d.add_argument("--out", default="parts.csv")

    s = sub.add_parser("scan")
    s.add_argument("--parts", default="parts.csv")
    s.add_argument("--out", default="listings.csv")
    s.add_argument("--demo", action="store_true")

    args = ap.parse_args()

    if args.cmd == "discover":
        try:
            discover(auth_or_die(), args.category, args.limit, args.out)
        except (RuntimeError, requests.RequestException) as e:
            die_on_api_error(e)
        return

    if args.demo:
        print("DEMO MODE — synthetic data")
        offers = demo_offers()
    else:
        token = auth_or_die()
        with open(args.parts, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("mpn")]
        offers = []
        for i, r in enumerate(rows, 1):
            print(f"  [{i}/{len(rows)}] {r['mpn']}")
            try:
                offers.extend(fetch_offers(token, r["mpn"]))
            except Exception as e:
                print(f"    ! {e}", file=sys.stderr)
            time.sleep(0.4)

    if not offers:
        sys.exit("No offers returned.")

    score(offers)
    write_csv(offers, args.out)
    report(offers, demo=args.demo)
    print(f"  rows -> {args.out}")
    if args.demo and demo_selfcheck(offers):
        sys.exit(1)


if __name__ == "__main__":
    main()
