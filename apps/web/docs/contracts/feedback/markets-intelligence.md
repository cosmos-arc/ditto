# Markets Intelligence contract feedback

- Retained the analytical strip, main evidence table, activity rail, analysis band, and the application's shared status bar. The frozen prototype has no rendered status-bar element, so it is not used as a geometry target.
- Experimental macro data is fail-closed: the page issues no read until the operator explicitly opts in and chooses a date range.
- AI summaries, capital-flow narratives, ratings, and forecasts were removed. The API does not report immutable snapshot identity, so the research-only warning remains visible.
- Reviewed geometry thresholds capture the taller opt-in strip and evidence-warning band that replace the prototype's fictional intelligence summaries.
