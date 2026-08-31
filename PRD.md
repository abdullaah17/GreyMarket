# PRD — Grey-Market Component Risk Scoring

**Status:** draft, pre-validation
**Version:** 0.1
**Date:** 31 August 2026
**Owner:** Abd

> **Read this first.** Sections 1–9 describe what the software does and
> are grounded in a working prototype. Sections 10–12 describe workflow,
> pricing and integrations, and are **hypotheses** — they encode guesses
> about how buyers work that no buyer has confirmed. They are marked
> `[ASSUMPTION]`. Treat them as things to disprove, not decisions made.

---

## 1. Summary

A tool that scores the counterfeit risk of an electronic component
purchase **before the order is placed**, using publicly available
marketplace data.

Today, counterfeit detection happens after money changes hands, in a
physical lab, per lot, slowly and expensively. This product moves one
part of that decision earlier and makes it free.

It does not replace lab testing. It decides which lots deserve one.

---

## 2. Problem

### 2.1 Why the grey market exists

Defence, aerospace, medical and industrial equipment stays in service
for 20–30 years. The semiconductors inside are discontinued after
roughly 8. When one fails, the original manufacturer no longer sells it.

Buyers are therefore *forced* into the open market — independent
distributors and brokers who source from unauthorized channels. There is
no alternative. The equipment must be repaired.

### 2.2 Why that market carries counterfeits

Some supply is legitimate old inventory. Some is chips harvested from
scrapped boards, sanded flat, re-marked with a fake part number and date
code, and resold as new. Recycled and re-marked parts pass visual
inspection and fail early in service.

Counterfeit electronic components are estimated to cost around
$200 billion annually across all sectors that use electronics.

### 2.3 What buyers do now

| Method | Cost | Limitation |
|---|---|---|
| Lab test (X-ray, decapsulation, chemical) | High, per lot | After purchase. Slow. Destructive sampling. |
| GIDEP lookup | Free to members | Government/qualified contractors only. Reports fakes already discovered. |
| Buy authorized only | Cheapest option | Impossible for discontinued parts. That's the whole problem. |
| Trusted broker relationships | Free | Relationship-based, not evidence-based. Doesn't scale. |

### 2.4 How much of the obsolete market S-1 can even apply to

**Measured, 1 September 2026.** "Obsolete" and "forced to the open
market" are not the same population, and the gap is large.

TI PDN 20231212001.3 lists roughly 200 discontinued devices. Applying
the selection rule in `CURATION.md` — a part qualifies only if the
authorized channel offers no way out — it yielded **zero** candidates.
Almost every entry is a `G4`/`E4`, tube or small-reel *variant*
retirement with a functionally equivalent part still sold through
authorized distributors. Two ADI notices were rejected the same way
(pin-to-pin replacement; RoHS package swap).

Notices that did qualify were structural: a dead foundry process, a
scaled-down fab, tooling past vendor end-of-support, with the
replacement column empty or the successor requiring redesign.

**Consequence for sizing.** The population where S-1 can fire at all is
a small fraction of the population of "obsolete parts", and the
counterfeit-cost figure in 2.2 covers all electronics, not this subset.
Any market size quoted from obsolescence volume will be far too large.
Size the market from *forced-to-broker* parts, and treat that fraction
as unmeasured — one notice is not an estimate.

This also validates the selection rule harder than a positive result
would have: a filter that rejects 200 parts on a stated principle is
discriminating, not decorative.

### 2.5 The gap

**Nothing scores risk before purchase.** Every existing control is
reactive. A buyer choosing between four brokers offering the same
obsolete part has no evidence-based way to rank them.

### 2.6 What existing products do

- **SiliconExpert** — large component reference database. Cross-references
  known GIDEP alerts against parts already on order. Aimed at large
  manufacturers. Reactive, and priced for enterprise.
- **ERAI** — industry body operating a member reporting database. Human
  reported, subscription, not a scoring engine.
- **Nexar / Octopart** — supply data aggregation. Provides the raw
  inventory and pricing feed. No risk analysis layer.

Nobody scores an individual broker or lot pre-purchase. That is the
space this product occupies.

---

## 3. Users and buyers

### 3.1 Primary user

**Component / sourcing engineer.** Given a part that must be found, they
identify supply options and decide which to trust. Technical, sceptical,
allergic to marketing claims. Will not use a tool that cannot show its
reasoning.

### 3.2 Buyer `[ASSUMPTION]`

Assumed to be the engineering or supply-quality manager one level above,
with a small tooling budget. **Unvalidated** — the budget may sit in
procurement, or in quality, or nowhere.

### 3.3 Segments, in order of accessibility

| Segment | Why they have the problem | Reachable from Pakistan? |
|---|---|---|
| Independent distributors | Fakes destroy their reputation; already pay for testing | Yes — smallest, most willing to talk |
| Medical device makers | 20-year lifecycles, regulated, forced grey-market buying | Yes |
| Industrial automation | Same lifecycle problem, high failure cost | Yes |
| Rail / marine | Long life, safety critical | Yes, slower |
| Utilities | Grid supply-chain regulation | Medium |
| Defence primes | Highest need | **No** — procurement and provenance barriers |

Defence is explicitly out of scope for v1 despite being the strongest
need. See section 13.

---

## 4. Product principles

1. **Show the evidence, never just a score.** A number a buyer can't
   interrogate is a number they won't act on. Every flag carries the
   rows that produced it.
2. **Never claim a part is counterfeit.** The product identifies
   *anomalies warranting inspection*. Asserting counterfeit status about
   a named seller invites defamation liability and is unsupportable from
   listing data alone.
3. **Public data only.** No customer data required to produce value.
   This removes the trust barrier for a first sale.
4. **Rank, don't gate.** Output is a prioritised list of what to test,
   not a buy/don't-buy verdict.

---

## 5. Scope

### v0.1 — prototype `[BUILT]`

- Discover obsolete parts by category
- Pull all seller offers per part
- Three anomaly signals
- CSV output, CLI

### v0.2 — research tool

- Seller-level profiling and aggregation
- Historical snapshots (detect stock appearing over time)
- Confidence weighting per signal
- HTML report suitable for showing a buyer

### v0.3 — first sellable version `[ASSUMPTION-heavy]`

- Bulk BOM upload, scored in one pass
- Watchlists and alerts
- Shareable per-part evidence pages
- Web UI

Everything past v0.2 is contingent on conversations that have not
happened. Do not build v0.3 from this document.

---

## 6. Functional requirements

### FR-1 Part input

**A curated part list is the primary input path.** Category discovery is
a convenience for exploration, not the collection strategy. This is an
inversion of the original plan and it is a design conclusion, not a
budget one.

The supply API exposes search, not filter. There is no way to express
"obsolete only" in the query, so discovery works by ranking a category
by relevance and then discarding everything that comes back Active.
Lifecycle is a rare attribute in a relevance-ranked result set, so the
caller pays per part returned and throws most of them away. That ratio
does not improve with a larger budget — it is inherent to using a search
endpoint to do a filter job. Measured: a 10-part probe of
`"microcontroller"` returned 10 parts, 100% ACTIVE, 0 kept.

- **FR-1.1** Accept a user-supplied part list. This is the path that
  every real run should use.
- **FR-1.2** Handle inconsistent lifecycle vocabulary across
  manufacturers (Obsolete / EOL / Discontinued / NRND). Implemented in
  `lifecycle.py` with a regression test over observed vendor strings.
- **FR-1.3** Given a category term, return parts whose lifecycle status
  indicates end-of-life. Exploration only; expect to discard most of
  what is fetched.
- **FR-1.4** Paginate to a requested limit; persist to CSV.
- **FR-1.5** Cap what is *fetched*, separately from what is *kept*. The
  API bills the former. `--limit` caps kept rows and is not a spend
  control; `--max-fetch` is.

### FR-2 Offer collection
- **FR-2.1** For each part, retrieve every seller offer available:
  seller name, authorization status, claimed inventory, price breaks.
- **FR-2.2** Tolerate partial failure — one bad part must not abort a
  200-part run.
- **FR-2.3** Respect API rate limits.
- **FR-2.4** Record retrieval timestamp on every row. *(Required for
  v0.2 historical analysis — capture it from v0.1 or the history is
  unrecoverable.)*

### FR-3 Signal scoring

Per part, compute authorized stock total, broker stock total, and median
price. Then evaluate each unauthorized offer. Full definitions in
section 7.

### FR-4 Output
- **FR-4.1** CSV with one row per offer, all inputs preserved.
- **FR-4.2** Sorted by flag count, then quantity.
- **FR-4.3** Terminal summary with the top offenders visible.
- **FR-4.4** Every flag traceable to the values that triggered it.

### FR-5 Offline mode
- **FR-5.1** `--demo` runs the full pipeline on synthetic data with no
  credentials, so scoring logic can be verified independently of API
  access.

---

## 7. Signal specification

This is the core intellectual property. Everything else is plumbing.

**Lifecycle is a four-value class, not a boolean:** `OBSOLETE`, `NRND`,
`ACTIVE`, `UNKNOWN`. S-1 through S-4 fire on `OBSOLETE` only. An NRND
part is still being manufactured, so an empty authorized channel is not
channel exhaustion — the stock can refill next week. NRND parts are
still collected and reported, as a separate observation, because zero
authorized stock on an in-production part is interesting for its own
reasons. Folding NRND into obsolete would dilute S-1.

Classification lives in `lifecycle.py` and is covered by a regression
test over real vendor strings (`python3 lifecycle.py`). Precedence is
`OBSOLETE > NRND > ACTIVE > UNKNOWN`, so "Discontinued — Not
Recommended for New Designs" is obsolete while "NRND / Last Time Buy"
is not.

### S-1 `phantom_stock`

```
part.lifecycle_class == OBSOLETE
AND authorized_stock == 0
AND offer.authorized == false
AND offer.quantity >= 1000
```

**Reasoning.** If no authorized distributor holds a single unit, the
legitimate channel is exhausted. A broker claiming four thousand units
must explain their origin. Legitimate answers exist — an OEM cancelled a
build, a distributor liquidated stock. Illegitimate ones exist too.
The claim is that this warrants a question, not that it proves fraud.

**Confidence:** high. This is the sharpest signal in the system.

### S-2 `outstocks_channel`

```
part.lifecycle_class == OBSOLETE
AND authorized_stock > 0
AND offer.quantity > authorized_stock * 10
AND offer.quantity >= 100          # absolute floor, S2_MIN_QTY
```

**Reasoning.** A weaker form of S-1 for parts with residual authorized
supply. One unauthorized seller holding an order of magnitude more than
the entire legitimate channel is anomalous.

**The multiple alone is near-worthless and the floor is load-bearing.**
Authorized stock on an obsolete part dwindles by definition — that is
what obsolescence is. A distributor down to 3 units is the normal case,
not an unusual one, and against that denominator any broker holding 31
units clears a 10x threshold. That is an obsolete part behaving exactly
as expected, and without a floor S-2 would fire on most of the catalogue
and mean nothing. The ratio only carries information once the absolute
quantity is non-trivial.

**Confidence:** low, and **S-2 is UNSCORED until it has a distribution.**
Decided before run 1, not after seeing its output.

Run 0 fired S-2 on 27% of offers (78/293), concentrated on parts whose
authorized stock was 3 and 8 units — where the 10x multiple clears at 30
and 80 and the floor of 100 barely binds. `S2_MIN_QTY = 100` is too low
to carry the intended meaning on a dwindling channel, and a dwindling
channel is precisely what a drained-vintage run 1 sample contains. Expect
S-2 to be noisier on run 1, not less.

The threshold is deliberately not changed on a 10-part sample. Reading a
signal already believed miscalibrated is how a threshold ends up set by
whatever the first sample happened to look like. Collect the distribution
of `broker_quantity / authorized_stock` across a real sample first, then
choose. `report()` prints an UNSCORED warning whenever S-2 exceeds 10% of
offers.

### S-3 `underpriced`

```
part.lifecycle_class == OBSOLETE
AND offer.authorized == false
AND offer.unit_price <= median_price * 0.5

where every price is read at the same quantity tier (REFERENCE_QTY = 1)
```

**Reasoning.** Scarcity raises prices. Obsolete parts appreciate. A
below-median price on a discontinued part inverts the expected economics.

**Price breaks must be compared at one tier.** Sellers publish
different numbers of price breaks, and the count is not random with
respect to the thing being measured: authorized distributors typically
publish many breaks, brokers typically one. Taking each seller's
cheapest break therefore compares a broker's single-unit price against a
distributor's volume price. That pulls the median down and suppresses
`underpriced` in exactly the direction that hides the anomaly. The
implementation reads every seller at `REFERENCE_QTY`, and records
`price_qty` and `price_break_count` so the asymmetry stays auditable.

**Confidence:** medium. Confounded by currency, condition, minimum order
quantity, and stale listings. The tier correction removes one known bias
but has not been checked against live data — verify the real break-count
gap between authorized sellers and brokers before tuning the 0.5
threshold.

### S-4 `catalogue_implausibility` `[BUILT]`

```
scanned_obsolete    = distinct parts in this run with lifecycle_class OBSOLETE
seller_obsolete     = distinct scanned_obsolete parts this unauthorized
                      seller claims stock of

share = seller_obsolete / scanned_obsolete

fires when  len(scanned_obsolete) >= 20  AND  share >= 0.30
```

**Reasoning.** A broker legitimately holding surplus stock holds a
*narrow* range — whatever they acquired. A seller claiming inventory
across hundreds of unrelated obsolete parts across many manufacturers is
either a pure intermediary listing stock they don't hold, or worse.
Requires no external data — it falls out of aggregating data already
collected.

**Confidence:** low until tested against real data. Two confounds, both
material, and both must be stated wherever this signal is shown:

1. **Sample-dependent.** The denominator is whatever this run happened
   to scan. Scan 200 microcontrollers and a microcontroller specialist
   scores high for entirely legitimate reasons. The share is a property
   of the query as much as of the seller.
2. **Cannot distinguish breadth from fabrication.** A large independent
   distributor with a genuinely broad book and a seller listing stock
   they do not hold produce the same number.

It is a ranking hint for which sellers to look at first. It is not
evidence about any seller, and per principle 2 it must never be
presented as one. The 0.30 threshold and the 20-part minimum are both
arbitrary and await real data.

Because the denominator is the scan, S-4 scores are comparable *within*
one run and not *across* runs. Do not store a seller's share as a
standing attribute.

### Signals explicitly rejected

- **Date code analysis** — requires physical inspection, not listings.
- **Image comparison of part markings** — needs photographs and a
  reference corpus. Later, possibly never.
- **GIDEP cross-reference** — access is restricted to government and
  qualified contractors. Not available.

---

## 8. Data model

```
Part
  mpn                 str    manufacturer part number, primary key
  manufacturer        str
  category            str
  lifecycle           str    raw vendor string, preserved verbatim
  lifecycle_class     enum   OBSOLETE | NRND | ACTIVE | UNKNOWN, derived

Offer
  mpn                 str    -> Part
  seller              str
  authorized          bool
  quantity            int    claimed inventory, self-declared
  unit_price          float  read at REFERENCE_QTY, not the cheapest break
  price_qty           int    tier the price was read at
  price_break_count   int    how many breaks the seller published
  currency            str
  retrieved_at        ts     stamped once per part fetch, so all rows
                             from one part share a retrieval time

PartAggregate         computed per part
  authorized_stock    int
  broker_stock        int
  median_price        float  median across offers read at one tier
  seller_count        int

SellerAggregate       computed per run, not per part
  seller              str
  obsolete_share      float  S-4; valid only within the run that made it

Flag
  offer_ref
  signal              enum   S-1 | S-2 | S-3 | S-4
  evidence            json   the values that triggered it
```

**Note on `quantity`.** Inventory levels are self-declared by sellers
and unverified. This is not a data quality problem to be solved — the
implausibility of the claim *is* the signal.

---

## 9. Architecture

```
  curated MPN list  ─────────────►  parts.csv     PRIMARY PATH
  (manual: PCN notices,                 │         hand-built, see s13
   distributor filters)                 │
                                        │
  Nexar API  ──►  discover  ────────────┤         exploration only
                  (search, not filter;  │         discards most of
                   bills what it        │         what it pays for)
                   discards)            │
                                        ▼
                                   fetch_offers
                                        │
                                        ▼
                                aggregate per part
                                        │
                                        ▼
                                 score (S-1..S-4)
                                        │
                           ┌────────────┴────────────┐
                           ▼                         ▼
                      listings.csv            terminal report
```

**Validated against live data, 1 September 2026.** A 10-part probe
confirmed the lifecycle attribute is present in Nexar responses, that
`lifecycle_from_specs` locates it, and that the vocabulary in
`lifecycle.py` matches real vendor strings: 10 parts returned, 0%
UNKNOWN, 100% ACTIVE, 0 kept. Everything from the API boundary through
classification is confirmed working on real data.

**Not validated.** Everything downstream of classification. No obsolete
part has passed through the scorer, so S-1 through S-4 and every
threshold in them have only ever seen synthetic data constructed to make
them fire. They remain unfalsified rather than verified.

**v0.1** — single Python file, CSV in/out, no database, no server.
Correct for the stage. Do not add infrastructure before there is a user.

**v0.2** — SQLite. Needed only when historical snapshots arrive, because
detecting *stock that appeared recently* requires storing yesterday.

**Dependencies:** `requests`. That is the entire dependency list and it
should stay close to that.

---

## 10. Workflow integration `[ASSUMPTION]`

Assumed: the engineer has a part number and a shortlist of sellers, and
wants them ranked before raising a purchase order.

**Unvalidated and material.** Possible alternatives:
- The decision is made in an ERP system and a separate tool is ignored.
- Broker choice is relationship-driven and evidence changes nothing.
- Sourcing is outsourced entirely to a distributor who owns the risk.

If the third is true, the buyer is the distributor, not the manufacturer,
and the entire go-to-market inverts. **Question 1 in every customer
conversation should establish which of these is real.**

---

## 11. Pricing `[ASSUMPTION]`

No pricing model is specified. Any number written here would be invented.

What must be learned first:
- What is currently spent on lab testing per year?
- What does one counterfeit incident cost?
- Who holds the budget?

Price against the cost of the incident, not against competitor pricing.
Nothing further can be said honestly today.

---

## 12. Non-goals

Explicitly out of scope. Each is a real request that will kill v1.

- Physical or lab-based authentication
- Verifying inventory claims against actual stock
- Any assertion that a specific part or seller is counterfeit
- ERP or PLM integration
- Marketplace or brokering function
- Blockchain provenance
- US defence procurement compliance (see 13)
- Mobile app
- Anything requiring customer data to function

---

## 13. Constraints

**GIDEP inaccessible.** Restricted to government agencies and qualified
contractors. The strongest known-bad dataset in the industry is
unavailable. Signals rest entirely on marketplace anomalies. This is a
material limitation and should be stated to customers, not hidden.

**Defence market gated.** US defence contracts carry foreign ownership
review and provenance requirements that a Pakistan-domiciled company
cannot satisfy. Defence is the strongest need and the least accessible
buyer. Entry is via medical, industrial and rail in Europe and Asia.

**API dependency.** Nexar is currently a single point of failure for all
input data. Acceptable at prototype stage, unacceptable as a business.
Mitigation deferred until there is a business.

**Validation has a floor cost, and it is above the free tier.** State
the arithmetic rather than the conclusion, so this can be recomputed
when either number changes:

```
parts needed for a meaningful S-1 read     ~200 obsolete parts
API cost via a curated list                ~1 part billed per part used
                                           -----------------------------
                                           ~200 parts of allowance

observed free allowance, evaluation app     10 parts
observed allowance, self-created app         0 parts
```

**Measured against run 0, 1 September 2026** — replacing the assumed
figures above with observed consumption:

```
parts requested                             54
parts that returned data before quota ran   10
offers returned                            293   (~30 offers per part)
```

Billing is per part with coverage, not per offer, so the ~1:1 ratio
holds and the free tier covers 10 parts. A 200-part run 2 therefore
needs roughly 20x the free allowance, and run 1 at 30–50 parts needs
3–5x it. Size any purchase against these numbers rather than the
estimate they replace.

Roughly a 20x shortfall against the observed free tier. The 200 figure
is the validation threshold in section 15 and is itself a judgement, not
a computed number; the ~1:1 ratio holds only on the curated-list path,
because category discovery bills for the Active parts it discards (see
FR-1). Both assumptions are worth re-checking before paying — a smaller
sample that still answers question 4 would lower the floor directly.

**Three runs, three different questions. Do not buy for a later one
before the earlier one has answered.**

| | parts | question it answers | run it when |
|---|---|---|---|
| Run 0 | 30–50 | Has the channel actually drained on recent withdrawals? | now; measures `authorized_stock`, does **not** test S-1 |
| Run 1 | 30–50 | Does `phantom_stock` fire *at all*? | only on a drained-vintage list (see below) |
| Run 2 | ~200 | Is the threshold any good? | only if run 1 came back positive |

**Run 0 exists because vintage is decisive, not incidental.** S-1
requires `authorized_stock == 0`. A part whose last-time-buy date has
only just passed still has authorized stock by construction, so an empty
S-1 result on a recent-vintage list is the overwhelmingly likely outcome
*whether or not the premise is true*. Running such a list against the
section 15 kill criterion would fire it for a reason it was not designed
to detect, and the honest response would be to override it — which is
the exact behaviour the criterion exists to prevent.

So the current `parts.csv` is not run 1 material. Of its 54 parts, 49
have a last-ship date in 2026–2029: by the vendor's own dates the
authorized channel is still open. Run it to *measure* `authorized_stock`
across the sample. That is cheap, informative, and consumes no kill
criterion. If authorized stock is non-zero nearly everywhere, the
vintage problem is confirmed with data and the required notice age
follows from it. If it is already zero in a meaningful fraction, those
parts become valid run 1 input.

These are not underpowered and full-strength versions of one
experiment. They answer different questions, and run 2 is worth nothing
until run 1 has returned a positive. A binary answer on the sharpest
signal is the thing worth buying right now; a tuned threshold on an
unanswered question is not.

Sequencing follows from that. Build the curated list first, then price
run 1 against a known part count. Buying an allowance before the list
exists purchases capacity against an unknown denominator, and it is the
tempting error because it is a purchase rather than an hour of work.
30–50 parts may exceed the free tier by little enough to make run 1 a
small spend rather than a real one.

**The obsolete part list is a manual dependency, and it gates the first
run.** Because a curated list is now the primary input (FR-1), somebody
has to build it: vendor PCN and EOL notices, distributor lifecycle
filters, obsolescence databases. This is hand work measured in hours and
it cannot be designed away — it is the input the entire pipeline runs
on. The first real run is gated on this, not on quota.

Curate for signal, not convenience. If S-1 is real anywhere, it is on
parts with **active repair demand and a dead authorized channel** —
semiconductors in long-life industrial, medical and rail equipment.
200 well-chosen obsolete MPNs is a better experiment than 2,000
arbitrary ones, and it costs less to run. That list is also the seed of
the product itself, so the hour spent building it is not overhead.

**Legal exposure.** Publishing seller-level risk scores is defamation
territory. Language must remain anomaly-based throughout — in the
product, the marketing, and any customer-facing report. Get counsel
before publishing seller rankings externally.

---

## 14. Open questions

Ordered by how much damage a wrong assumption does.

1. Who owns the buy-versus-test decision, and do they have budget?
2. What does a counterfeit incident actually cost, in money and delay?
3. Is broker selection evidence-driven or relationship-driven?
4. Does `phantom_stock` correlate with anything real, or is surplus
   inventory simply common?
5. Would a buyer act on a signal that carries no known-bad confirmation?
6. Does the same problem exist outside electronics — aerospace
   fasteners, bearings, valves?

Questions 1–3 are answered by conversations. Question 4 is answered by
running the tool. They are independent and should run in parallel.

---

## 15. Success and kill criteria

### Validation stage

**Continue if:**
- 20+ phantom_stock instances across 200 obsolete parts
- 3+ of 10 interviewees describe pre-purchase risk as an unsolved problem
- At least one names a specific incident with a cost attached

**Kill if:**
- Zero `phantom_stock` hits across 30–50 *well-chosen, drained-vintage*
  obsolete parts (run 1, section 13). This counts as evidence against
  the premise, not as an underpowered sample. Lifecycle parsing is
  confirmed working against live data (section 9), which was the only
  legitimate reason to discount an empty result — so that explanation is
  spent. Treating an empty run 1 as "too small to tell" and proceeding
  to run 2 anyway is how these criteria stop being falsifiable.

  **Pre-registered exception, written before any run.** This criterion
  applies only to a list whose authorized channel has had time to drain.
  It does not fire on a list where the channel is still open, because
  S-1 cannot fire there by construction.

  The condition is quantitative and must not be invoked qualitatively:

  ```
  the criterion applies only if, across the sample,
  authorized_stock == 0 for at least half the parts
  ```

  Measure that with run 0 *before* run 1. If the sample fails the
  condition, run 1 has not been run — collect an older list and try
  again. Invoking "the vintage was wrong" after seeing an empty result,
  rather than testing it beforehand, is an excuse and is indistinguish-
  able in this document from a pre-registered condition. That is why the
  test is named here and why run 0 comes first.

  **A run has three outcomes, not two.** The condition above was written
  to stop an *empty* result being explained away. It does not cleanly
  govern a sample that fires hard on the one part meeting S-1's
  precondition — a different situation, and one that has already
  occurred (run 0, 1 September 2026).

  | outcome | meaning |
  |---|---|
  | supported | condition met, `phantom_stock` fires |
  | not supported | condition met, `phantom_stock` does not fire — **this is what kills** |
  | could not test | condition not met; the sample says nothing either way |

  "Could not test" is not a weak "not supported". Record which one
  occurred, because a future reader seeing `run 1 INVALID` next to a
  positive observation needs to know which kind of invalid it was.

  **A drained part resting on one authorized offer does not count as
  drained.** Remove that single inventory line and the part becomes
  `no_authorized_coverage`, the state excluded from scoring — so one
  seller is all that separates "channel exhausted" from "artefact". The
  drained count therefore requires **at least two authorized sellers,
  all at zero**. Reported separately as `drained/thin`, and excluded
  from the fraction the condition is measured on.

  This is not hypothetical. Run 0's single drained part had exactly one
  authorized offer; under the robust definition the drained fraction is
  0%, not 10%.

  **Run 1 collection requirement.** The 2019–2022 list must be curated
  for parts likely to carry *several* authorized sellers, so that "all
  at zero" is a statement about the channel rather than about one
  seller's listing.
- Fewer than 5 anomalies across 200 parts (run 2)
- Interviewees consistently say broker choice is relationship-based
- The problem is real but sits entirely with distributors who already
  test everything and see no gap

### Build stage `[hypothetical]`

- 3 companies pay for manually produced reports before any UI exists
- 1 documented case where output changed a purchasing decision

Manual delivery precedes automation. If nobody pays for the output,
nobody will pay for the tool that generates it.
