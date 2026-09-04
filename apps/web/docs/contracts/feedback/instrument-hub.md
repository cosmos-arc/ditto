# Instrument Hub contract feedback

- Retained the frozen object-hub shell and its meta, tabs, main, and bottom bands.
- Replaced demo price, PE/PB, industry, peers, news, and halt content with public instrument identity and exact date-range bars.
- Bars are explicitly non-experimental and unadjusted. Because the bars contract has no immutable snapshot identity, the UI keeps a decision-use warning visible.
- Prototype overlays were removed from the React contract: none has a stable public API. Data-boundary content is inline instead of opening empty drawers.
- The React main band deliberately uses the 340px prototype sidebar width because the related/signals/notes rail has no public contract. The bottom band collapses from the prototype's 194px demo timeline to a 36px evidence boundary instead of reserving empty space; the page-specific geometry thresholds record these two reviewed deviations.
