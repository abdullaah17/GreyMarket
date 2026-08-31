# Curating the obsolete parts list

`parts.csv` is the primary input to the pipeline (PRD FR-1.1). It is built by
hand from vendor discontinuance notices. This file records how, so the list can
be extended without re-deriving the selection rule.

## The rule: no replacement, sole source

A part only earns a place if **the authorized channel offers no way out**.
S-1 claims the legitimate channel is exhausted and asks where a broker's
thousands of units came from. That claim is only interesting when a buyer is
genuinely forced to the open market.

Reject a part if any of these is true:

- **A pin-to-pin replacement is offered.** The buyer orders the replacement
  from an authorized distributor. Nobody is forced anywhere.
- **Only a package or variant is withdrawn.** Tape-and-reel changes, RoHS
  conversions, leaded-package retirements, `G4`/`E4` suffix cleanups. The
  function is still sold.
- **Multiple sources exist.** A second manufacturer makes an equivalent.

Prefer a part when:

- **Full Withdrawal**, not version withdrawal
- **Non-Manufacturable** — the vendor cannot produce more at any price
- **Sole Source** — no second manufacturer
- **Replacement column empty**, or a successor requiring hardware/software
  redesign, which is a cost wall rather than a drop-in
- The reason is structural and permanent: a dead foundry process, a shut-down
  fab node, tooling past end-of-support

## Curate for signal, not convenience

If S-1 is real anywhere, it is on parts with **active repair demand and a dead
authorized channel**. Bias toward semiconductors in equipment with 20–30 year
service lives: industrial drives and motor control, machine controllers,
industrial networking, HMI panels, rail. 200 well-chosen MPNs beat 2,000
arbitrary ones and cost less to scan.

This build targets **industrial automation** as a single vertical, so the list
doubles as something to show one sourcing engineer who recognises the parts.

## Provenance

Every row carries `source_notice` and `source_url`. Nothing goes in that cannot
be traced to a published notice. A part number that cannot be sourced is not
added, however plausible it looks — an unverifiable MPN silently poisons the
experiment it is supposed to inform.

## Verification status

- Transcribed from the two notices cited in `parts.csv`.
- Spot-checked against NXP part pages: `DSP56F805FV80E` ("16-bit DSC, 56800
  core") and `MPC8247CVRMIBA` ("PowerQUICC ... -40 to 105C"). Both resolve and
  match their application labels.
- **Not exhaustively re-verified line by line.** Before spending API quota,
  re-read the source notices and confirm the full list.

## Extending

Sources that yield this profile:

- NXP PCN portal — filter for Full Withdrawal + Non-Manufacturable
- ADI PDN library — foundry/process-driven obsolescence
- Renesas/IDT/Intersil product lifecycle notices — some state
  "there will be no replacement part"
- TI PDN notices — mostly variant withdrawals with drop-in replacements, so
  low yield under this rule

Append to `parts.csv` with the same columns. `greymarket.py scan` reads the
`mpn` column and ignores the rest, so provenance costs nothing at runtime.

## Vintage: the second filter, and it is decisive

The selection rule above says *whether* a part can force a buyer to a
broker. Vintage says *whether it has happened yet*.

S-1 requires `authorized_stock == 0`. A part whose last-time-buy date has
only just passed still has authorized stock by construction. It satisfies
every criterion above and still cannot produce an S-1 hit. Filter on
`last_time_ship`, not just on the selection rule.

The list as built shows the problem plainly — 49 of 54 parts have a last-ship
date in 2026–2029, so by the vendor's own dates the channel is still open:

| last_time_ship | parts | state |
|---|---|---|
| 2022-05-31 | 5 | drained, ~4 years |
| 2026-02-27 | 6 | still draining |
| 2027-01-30 and later | 43 | still draining |

Use this list for **run 0** (measure `authorized_stock`), not run 1. See
PRD sections 13 and 15 — the kill criterion is pre-registered to apply only
to a sample where `authorized_stock == 0` for at least half the parts.

For run 1, collect 2019–2022 full withdrawals under the same selection rule.

## Rejected sources, and why

- **TI PDN 20231212001.3** — ~200 devices, zero candidates. Variant
  retirements with functionally equivalent replacements still sold.
- **ADI PDN 23_0120, 22_0028** — pin-to-pin replacement; RoHS package swap.
- **Digi-Key-hosted scan of NXP 202211001DN** — *extraction quality*, not
  selection. The PDF parses with corrupted part numbers (`MCB9808GBMAE`,
  `MC53212988577`), 12NC codes bleeding into the part-number column, and
  "Sale Source" where the notice reads "Sole Source". A garbled MPN that
  happens to land on a different real part fails silently, which is the one
  transcription error that does not announce itself.

  **Prefer the vendor's own HTML notice pages.** `nxp.com/pcn/<id>` and
  `analog.com/media/en/PCN/*.pdf` both extracted cleanly; distributor-hosted
  PDF scans did not.

## Guard against a silent transcription error

A mistyped MPN usually returns no match, which is visible. The dangerous case
is a typo landing on a different real part — plausible in these families,
where suffixes encode temperature grade and package (`DSP56F805FV80E` vs
`DSP56F805FV80`).

When `scan` returns results, check the manufacturer on each row against the
`manufacturer` column here. A wrong-but-real MPN often keeps the right
manufacturer, so also spot-check that the returned part family matches the
`family` column. Rows whose manufacturer disagrees with the notice are
transcription errors, not market findings.
