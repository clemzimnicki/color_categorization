# legacy/as_run_colors.json

`ADJUSTED_COLORS_1` and `ADJUSTED_COLORS_2`, moved verbatim out of `index.html`.

These define the **exact colors shown** to the first 25 participants in the
triplet task (20 on monitor 1 / near_door, 5 on monitor 2 / far_door), before
the color-runtime refactor described in `COLOR_REFACTOR_BRIEF.md`. They were
produced by the wrong pipeline (the adjusted xyY re-encoded through standard
sRGB, rather than through the monitor's measured gun characterization), which
is the bug that refactor fixes — but they are exactly what those 25
participants actually saw on screen, so they are required for any salvage
analysis of that data.

Do not edit or regenerate this file. Do not delete it, even after the
corrected renderer (`color_rendering/renderColor.js`) is fully rolled out.
