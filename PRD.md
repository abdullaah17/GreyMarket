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

### 2.4 The gap

**Nothing scores risk before purchase.** Every existing control is
reactive. A buyer choosing between four brokers offering the same
obsolete part has no evidence-based way to rank them.

### 2.5 What existing products do

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

### FR-1 Part discovery
- **FR-1.1** Given a category term, return parts whose lifecycle status
  indicates end-of-life.
- **FR-1.2** Handle inconsistent lifecycle vocabulary across
  manufacturers (Obsolete / EOL / Discontinued / NRND).
- **FR-1.3** Accept a user-supplied part list as an alternative input.
- **FR-1.4** Paginate to a requested limit; persist to CSV.

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

### S-1 `phantom_stock`

```
part.lifecycle is obsolete
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
part.lifecycle is obsolete
AND authorized_stock > 0
AND offer.quantity > authorized_stock * 10
```

**Reasoning.** A weaker form of S-1 for parts with residual authorized
supply. One unauthorized seller holding an order of magnitude more than
the entire legitimate channel is anomalous.

**Confidence:** medium. Threshold is arbitrary and needs tuning against
real data.

### S-3 `underpriced`

```
part.lifecycle is obsolete
AND offer.authorized == false
AND offer.unit_price <= median_price * 0.5
```

**Reasoning.** Scarcity raises prices. Obsolete parts appreciate. A
below-median price on a discontinued part inverts the expected economics.

**Confidence:** medium. Confounded by currency, condition, minimum order
quantity, and stale listings.

### S-4 `catalogue_implausibility` `[PLANNED — v0.2]`

```
count of distinct obsolete parts one seller claims stock of
```

**Reasoning.** A broker legitimately holding surplus stock holds a
*narrow* range — whatever they acquired. A seller claiming inventory
across hundreds of unrelated obsolete parts across many manufacturers is
either a pure intermediary listing stock they don't hold, or worse.

**This is likely the strongest signal in the system**, and it requires
no external data — it falls out of aggregating data already collected.
Build it next.

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
  lifecycle           str    raw vendor string
  is_obsolete         bool   derived

Offer
  mpn                 str    -> Part
  seller              str
  authorized          bool
  quantity            int    claimed inventory, self-declared
  unit_price          float
  currency            str
  retrieved_at        ts

PartAggregate         computed per part
  authorized_stock    int
  broker_stock        int
  median_price        float
  seller_count        int

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
  Nexar API  ──►  discover  ──►  parts.csv
                                     │
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
- Fewer than 5 anomalies across 200 parts *with lifecycle parsing
  verified working*
- Interviewees consistently say broker choice is relationship-based
- The problem is real but sits entirely with distributors who already
  test everything and see no gap

### Build stage `[hypothetical]`

- 3 companies pay for manually produced reports before any UI exists
- 1 documented case where output changed a purchasing decision

Manual delivery precedes automation. If nobody pays for the output,
nobody will pay for the tool that generates it.
