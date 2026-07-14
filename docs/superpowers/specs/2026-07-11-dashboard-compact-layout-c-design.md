# Dashboard Compact Layout C Design

Date: 2026-07-11
Status: approved direction, not implemented yet

Review status: optimized after risk review

## Goal

Make the V2 dashboard fit the important workshop state into one screen, with less text, consistent styling, and drawers/tabs for secondary detail.

The operator should quickly see:

- which machines are open
- what is running now
- what needs attention
- done count or m2 for the selected date range
- top customers by file-name customer code

One-screen target means the default desktop view should fit the header, sidebar, production board, and key badges in the first viewport at `1161x789`. Detail lists and charts may require opening a tab/drawer.

## Chosen Layout

Use Layout C: fixed left sidebar plus main work area.

Left sidebar:

- machine status card
- quick statistics card
- top customer card

Main area:

- icon/tab row
- production board tab
- attention tab
- machine flow tab
- customer statistics tab

Default view is production board.

Critical attention state must not be hidden. Even when the attention tab is closed, the header or sidebar must show a red attention badge with the count. If any high-severity item exists, the badge is red and visible in the first viewport.

## Header

Keep one compact header row:

- app name: `Xuong V2`
- date quick filter
- machine filter
- metric switch: `So luong` / `m2`
- small icon buttons for refresh, admin, and realtime status

Use icons where text does not add value. Keep tooltips or short titles for unfamiliar icons.

Icon-only buttons must have `title` and `aria-label`. Critical state text such as `Dang mo`, `Chua mo`, and `Can xu ly` should remain readable text, not icon-only.

## Sidebar

Machine card:

- show `InBat`, `InDecal`, `CNC`
- show only open state and V2 state in collapsed form
- click/expand for version, ping, latest machine log, latest admin action, and outbox detail

Quick statistics card:

- total by current metric
- per-machine values
- estimated bad m2 rate as a small secondary line
- attention count as a small badge if there are items to review

Customer card:

- top customers from file names for now
- use same date and machine filters
- support count and m2 metric
- future QCVL connection may replace the source without changing the UI shape

If customer data is too crowded, show only the top 5 in the sidebar. The full top 10 goes in the customer tab.

## Main Tabs

Production tab:

- compact board with primary production states
- card height stays small
- card shows machine color, shortened file name, and time
- hover shows image only
- click pins image plus detail
- double click or admin action opens full detail modal if needed

Default compact board should use four visual columns:

- `Cho xu ly`: combines exported and RIP, with small status chips inside each card
- `Dang chay`: printing/cutting
- `Da xong`: completed jobs
- `Van de`: cancel/error/delete/action needed

The old six-state detail (`Xuat`, `RIP`, `Dang chay`, `Da xong`, `Loi/Huy`, `Xoa`) should still be available inside a drawer or detail view. Do not delete the underlying status model.

Attention tab:

- list all attention items
- grouped by severity and machine color
- no full list on default screen unless user opens this tab
- red count badge is always visible in the sidebar/header

Flow tab:

- current machine completion flow chart
- metric switch controls count or m2
- colors stay consistent:
  - InBat: green `#22c55e`
  - InDecal: blue `#3b82f6`
  - CNC: red-orange `#ff6347`

Customer tab:

- top customer chart from file-name parsing
- toggle count or m2
- later QCVL integration can add canonical customer names
- show top 10 plus totals by selected date/machine filter

## CSS Rules

Use one visual language from top to bottom:

- same card radius: 8px
- same panel background and border colors
- same machine colors everywhere
- same spacing scale
- icon buttons instead of long text buttons when meaning is obvious
- drawers/tabs for secondary detail
- no decorative gradients or unrelated visual effects

## Data Source

Initial customer statistics source:

- parse customer code from file name, same as current statistics logic
- use existing `/api/stats` date and machine filters
- backend must return customer count and customer m2, because current customer data only returns job count
- customer m2 should use the same `parse_area_python` and `billable_runs` logic as current machine m2 statistics
- files that cannot be parsed into a customer code should go to `UNKNOWN`, not crash or disappear
- customer labels should be shortened in the sidebar but full labels should remain available in the customer tab tooltip/detail

Date range behavior:

- all charts and sidebar totals use the same selected date and machine filter
- ranges that include future dates should stop at the current date for charts
- `Toan thoi gian` should start at `2000-01-01` and end at the current date

Future source:

- QCVL customer data can replace or enrich parsed file-name customer codes
- dashboard UI should not depend on QCVL during this phase

## Risks

- Layout C changes user habit more than Layout A.
- One-screen target depends on actual monitor size; board height and drawer defaults must be tested in the real browser at `1161x789` and wide desktop.
- Customer parsing from file names may be imperfect until QCVL is connected.
- Too many hidden drawers can hide production issues; keep high-severity attention visible as a badge.
- Moving CSS/HTML too much at once can break the live dashboard; deploy the redesign in small steps and restart Dashboard only.

## Implementation Guardrails

- Do not touch QCVL in this phase.
- Do not restart production server unless required; Dashboard-only restart is preferred.
- Keep existing `/api/data`, `/api/stats`, and `/api/v2_status` usable while adding new fields.
- Use a small frontend state object so `/api/data`, `/api/stats`, and `/api/v2_status` do not overwrite each other unpredictably.
- Keep old detail modal and admin actions working.
- Keep hover/click preview behavior working.
- Add tests before changing data behavior.

## Verification

Before deploy:

- unit tests for stats/customer data
- py_compile Dashboard
- build Dashboard.exe
- deploy Dashboard only, not server
- browser check at `http://192.168.1.104:5000/`
- verify no console errors
- verify default screen fits `1161x789` without important overlap
- verify default screen also works on wide desktop
- verify metric toggle updates sidebar, flow chart, and customer chart
- verify attention badge remains visible when attention tab is closed
- verify admin detail actions still open and submit
- verify customer chart changes between count and m2
