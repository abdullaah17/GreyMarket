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
