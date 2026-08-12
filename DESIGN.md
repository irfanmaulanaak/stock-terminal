# Stock analytics redesign

## Visual thesis

This dashboard is a quiet research instrument: the first decision is what deserves attention, and the rest of the interface supplies context without competing for it. The watchlist opens on a compact, amber-marked Top 5 Focus shortlist; the full universe and the portfolio remain available underneath the same read-only workspace.

The visual language is warm charcoal, editorial spacing, thin rules, and restrained signal color. Numbers and timestamps use a monospace face so market metadata reads as data rather than decoration. Amber identifies focus and uncertainty; green and red are reserved for directional or P/L semantics.

## Tokens

- Background: `#171513`
- Surface: `#211e1a`
- Soft surface: `#28231e`
- Rule: `#40382f`
- Primary text: `#eee8df`
- Secondary text: `#9c9185`
- Focus amber: `#e2a64b`
- Positive green: `#72c78a`
- Negative red: `#df7570`
- Metadata face: system monospace stack (`--mono`)

## Prohibitions

- No large gradient hero, atmospheric background, or ornamental charting.
- No stacked card grid that makes every metric compete with the shortlist.
- No blue/cyan accent system; amber owns focus and green/red retain semantic meaning.
- No implied certainty: preserve “Not a buy order / no guarantee” and the methodology disclosure.
- No changes to the read-only API, quote refresh behavior, filters, sorting, or portfolio calculations.
