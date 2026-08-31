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
from dataclasses import dataclass, asdict, field

import requests

TOKEN_URL = "https://identity.nexar.com/connect/token"
API_URL = "https://api.nexar.com/graphql"

# Lifecycle strings that mean "not made anymore". Vendors spell these
# inconsistently, so we match loosely.
DEAD_STATUSES = {"obsolete", "eol", "end of life", "discontinued",
                 "not recommended for new designs", "nrnd"}

BROKER_QTY_SUSPICIOUS = 1000
PRICE_RATIO_SUSPICIOUS = 0.5


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
    # filled in during scoring
    authorized_stock: int = 0
    broker_stock: int = 0
    price_ratio: float | None = None
    flags: list = field(default_factory=list)

    @property
    def score(self) -> int:
        return len(self.flags)

    @property
    def is_dead(self) -> bool:
        return self.lifecycle.strip().lower() in DEAD_STATUSES


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


def lifecycle_from_specs(specs) -> str:
    """Lifecycle lives in the spec bag and the key name varies."""
    for s in specs or []:
        name = ((s.get("attribute") or {}).get("shortname") or "").lower()
        if "lifecycle" in name or name in {"status", "partstatus"}:
            return s.get("displayValue") or ""
    return ""


# ----------------------------------------------------------------------
# discover
# ----------------------------------------------------------------------

def discover(token: str, category: str, limit: int, out: str) -> None:
    """Walk a category, keep only the parts that are no longer made."""
    found, start, page = [], 0, 100
    while len(found) < limit and start < 1000:
        data = gql(token, DISCOVER_QUERY,
                   {"q": category, "limit": page, "start": start})
        results = (data.get("supSearch") or {}).get("results") or []
        if not results:
            break
        for r in results:
            part = r["part"]
            lc = lifecycle_from_specs(part.get("specs"))
            if lc.strip().lower() in DEAD_STATUSES:
                found.append({
                    "mpn": part["mpn"],
                    "manufacturer": (part.get("manufacturer") or {}).get("name", ""),
                    "category": (part.get("category") or {}).get("name", ""),
                    "lifecycle": lc,
                })
        start += page
        print(f"  scanned {start}, kept {len(found)}")
        time.sleep(0.4)

    found = found[:limit]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["mpn", "manufacturer",
                                          "category", "lifecycle"])
        w.writeheader()
        w.writerows(found)
    print(f"\n{len(found)} obsolete parts -> {out}")
    if not found:
        print("Nothing found. Check the lifecycle field name in "
              "lifecycle_from_specs() against Nexar's current schema.")


# ----------------------------------------------------------------------
# scan
# ----------------------------------------------------------------------

def fetch_offers(token: str, mpn: str) -> list[Offer]:
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
            if not prices:
                continue
            best = min(prices, key=lambda p: p.get("price", float("inf")))
            out.append(Offer(
                mpn=part.get("mpn", mpn), manufacturer=mfr, lifecycle=lc,
                seller=name, authorized=auth,
                quantity=int(offer.get("inventoryLevel") or 0),
                unit_price=float(best.get("price") or 0),
                currency=best.get("currency") or "USD"))
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
                o.price_ratio = round(o.unit_price / median, 3)

            if o.authorized or not o.is_dead:
                continue

            # the core signal: nobody legitimate has it, this guy has piles
            if auth_stock == 0 and o.quantity >= BROKER_QTY_SUSPICIOUS:
                o.flags.append("phantom_stock")

            # broker holds more than the entire authorized channel
            if auth_stock > 0 and o.quantity > auth_stock * 10:
                o.flags.append("outstocks_channel")

            # obsolete parts get more expensive, not cheaper
            if (o.price_ratio is not None
                    and o.price_ratio <= PRICE_RATIO_SUSPICIOUS):
                o.flags.append("underpriced")


def report(offers: list[Offer]) -> None:
    parts = {o.mpn.upper() for o in offers}
    dead = {o.mpn.upper() for o in offers if o.is_dead}
    phantom = [o for o in offers if "phantom_stock" in o.flags]
    flagged = [o for o in offers if o.flags]

    print("\n" + "=" * 66)
    print("RESULT")
    print("=" * 66)
    print(f"  parts              {len(parts)}  ({len(dead)} obsolete)")
    print(f"  offers             {len(offers)}")
    print(f"  flagged            {len(flagged)}")
    print(f"  phantom stock      {len(phantom)}")

    if phantom:
        print("\n  obsolete, zero authorized stock, broker claims piles:\n")
        for o in sorted(phantom, key=lambda x: -x.quantity)[:12]:
            ratio = f"{o.price_ratio:.2f}x" if o.price_ratio else "-"
            print(f"    {o.mpn:<18} {o.seller:<24} "
                  f"{o.quantity:>7} units   {ratio:>7} median")

    print("\n  VERDICT")
    if len(phantom) >= 20:
        print("    Strong. The anomaly is real and common.")
        print("    Now go show these rows to a buyer.")
    elif len(phantom) >= 5:
        print("    Present but thin. Widen the part list.")
    else:
        print("    No signal. Check that lifecycle parsing actually worked")
        print("    before you conclude the idea is dead.")
    print()


# ----------------------------------------------------------------------

def demo_offers() -> list[Offer]:
    rng = random.Random(7)
    auth_names = ["Digi-Key", "Mouser", "Arrow"]
    brokers = ["Apex Components", "Zenith Electronics", "Sunrise Semi",
               "Global Parts Exchange", "Meridian Supply"]
    out = []
    for i in range(25):
        mpn = f"SYNTH-{1000+i}"
        base = rng.uniform(3, 60)
        dead = rng.random() < 0.7
        lc = "Obsolete" if dead else "Active"
        starved = dead and rng.random() < 0.6
        for d in rng.sample(auth_names, 2):
            out.append(Offer(mpn, "DemoCorp", lc, d, True,
                             0 if starved else rng.randint(50, 900),
                             round(base * rng.uniform(0.95, 1.1), 4)))
        for b in rng.sample(brokers, rng.randint(2, 4)):
            odd = starved and rng.random() < 0.6
            out.append(Offer(mpn, "DemoCorp", lc, b, False,
                             rng.randint(2000, 9000) if odd else rng.randint(5, 600),
                             round(base * (rng.uniform(0.2, 0.45) if odd
                                           else rng.uniform(1.2, 3.0)), 4)))
    return out


def write_csv(offers: list[Offer], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(offers[0]).keys()))
        w.writeheader()
        for o in sorted(offers, key=lambda x: (-x.score, -x.quantity)):
            d = asdict(o)
            d["flags"] = "|".join(o.flags)
            w.writerow(d)


def auth_or_die() -> str:
    cid, sec = os.getenv("NEXAR_CLIENT_ID"), os.getenv("NEXAR_CLIENT_SECRET")
    if not (cid and sec):
        sys.exit("Set NEXAR_CLIENT_ID and NEXAR_CLIENT_SECRET (or use --demo)")
    return get_token(cid, sec)


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
        discover(auth_or_die(), args.category, args.limit, args.out)
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
    report(offers)
    print(f"  rows -> {args.out}\n")


if __name__ == "__main__":
    main()
