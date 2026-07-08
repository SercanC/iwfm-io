# IWFM file-format gotchas

## Dates
- IWFM date strings: `MM/DD/YYYY_HH:MM`, and **hour 24:00 means end of
  day** (`09/30/2021_24:00` == 2021-10-01 00:00). Use
  `iwfm.io._tokens.parse_iwfm_date` / `format_iwfm_date`, never bare
  `strptime`.
- DLL date arrays are Excel serial days (days since 1899-12-30);
  convert with `iwfm.plots.excel_date_to_datetime`.

## Text input files
- Comment lines start with `C`, `c`, `*`, or `/` **in column 1 only** —
  a line starting with whitespace is data even if a `/` appears later.
- Data lines end with `/ KEYWORD description`; the same section can
  have different entries across IWFM versions (2015 vs 2024+), so
  `iwfm.io` readers match keywords, not positions.
- Child-file paths inside component files are relative to the
  **Simulation working directory**, not the component file's folder.
- Element rows list 4 nodes; `node4 == 0` means a triangle.

## Outputs: text vs HDF
- A fresh run of the Simulation executable writes budget/zbudget
  **HDF** files plus text heads (`*HeadAll.out`); the Budget/ZBudget
  post-processors turn HDFs into human-readable text (`.bud`).
  Distributed models sometimes ship only the text versions —
  `open_model` surfaces HDF budgets automatically, text budgets are
  read with `read_budget_text`.
- Budget HDF locations list alphabetically (Subregion 1, 10, 11, …, 2)
  — match by name/id, never by position.
- Monthly outputs use calendar months; `iwfm-io` ≥ 1.1.1 builds correct
  calendar DatetimeIndexes (older versions drifted).

## Units
- Budget HDF values are model-internal (typically cubic feet for
  volumes); the conversion factors live in each component main file
  (e.g. GW main `FACTVLOU`, commonly `2.2957e-5` → acre-feet). Text
  `.bud` files are already converted.
- Aquifer parameters carry factors `FKH FS FN FV FL` from the GW main;
  the adapter applies them.

## DLL specifics
- `IWFMModel(preprocessor_file=...)` takes the preprocessor **main .IN
  file** — passing the `.bin` fails with "error reading integer data at
  or around line 10".
- The DLL is version-sensitive: a 2025.0 DLL cannot read a 2024.2
  `PreprocessorOut.bin` (regenerate with a matching PreProcessor exe,
  or just use `open_model`, which reads text inputs from any version).
- Inquiry mode (`is_for_inquiry=True`) cannot serve supply/demand,
  tile drains, bypasses, ag crops, or live stream–GW exchange — the
  wrapper raises clean errors, and the adapter provides file-based
  equivalents for all of them.
- IWFM 2024.2+ simulation executables do **not** write
  `IW_ModelData_ForInquiry.bin`; the first DLL inquiry open creates it
  (slow full instantiation once, fast afterwards).
