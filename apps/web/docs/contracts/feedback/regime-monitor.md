# Regime monitor implementation feedback

- React route: `/research/regime`
- Contract verification: 2026-08-30
- The React page replaces the prototype's static market claims with the generated `/api/v1/market/regime` response. Mock and live modes use the same DTO mapper, query hook, and workspace.
- Diagnostics fail closed until an immutable snapshot id, exact manifest hash, benchmark instrument, start date, end date, and knowledge cutoff are all bound. The full scope is part of both the cache key and request.
- End-of-day semantics require `end_date < knowledge_cutoff`; the backend verifies the manifest and every bars input hash and excludes the cutoff-day close.
- The first supported model is deliberately limited to `momentum-20d-v1`. The page does not present IVIX, northbound flow, breadth, macro drivers, strategy attribution, or executable advice because those contracts do not exist.
- [proto-deviation] The prototype AI drawer is represented by an evidence-scope sheet. This preserves the prototype's triggerable overlay and operator flow while avoiding an ungoverned AI interpretation surface.
- [proto-deviation] The prototype status bar is not duplicated inside the route because the application shell already owns global status. The page uses a 42px evidence strip, chart-first workspace, source rail, and transition band. The transition band is an implementation enhancement and is not falsely paired to the prototype chart's 22px mini-timeline in geometry audits.
- No generic market-condition service, new persistence layer, implicit latest query, or parallel scoring implementation was introduced.
