# Task brief: robust, runtime color rendering for the triplet task

## 0. Read this first — what you are and aren't doing

You are refactoring **how the triplet task turns a color identity into light on
screen**. Today the experiment ships *precomputed hex codes* (the big
`ADJUSTED_COLORS_1` / `ADJUSTED_COLORS_2` literals in `index.html`) that were
produced by an offline script through the **wrong** color pipeline (standard
sRGB) instead of the monitor's measured **gun** pipeline. The fix is to stop
precomputing colors and instead compute them **at runtime from one shared
renderer** driven by each monitor's measured characterization.

This is a correctness refactor on a **live study**. Data has already been
collected with the wrong colors (20 participants on one monitor, 5 on the
other). That data and the record of what those participants saw **must be
preserved, not deleted**. See §2.

**Do not run destructive commands and do not run the experiment or any build
without asking the human first.** Work on a branch, commit in small steps,
and produce a diff for review.

---

## 1. The core idea

Separate three things the current code conflates:

1. **Identity** — a stable label per color. In this repo the identity is the
   6-hex string embedded in the `img_triplets/XXXXXX.png` identifiers used in
   `colorNames.json`, `checkTrials.json`, `validationPicked.json`,
   `validationRandom.json`, and recorded in every data row. **Identity never
   changes and no item/data file is edited.** The `.png` suffix is vestigial —
   the triplet task renders inline `<div>` squares, not images — but it is part
   of the recorded identifier, so leave it exactly as is.

2. **Specification** — the device-independent target for each identity, in CIE
   **xyY**. One canonical file. No monitor adjustments baked in.

3. **Rendering** — a single function `renderColor(target, calib, identity)` that
   maps xyY (+ that monitor's per-color adjustment) → device RGB using that
   monitor's measured primaries and gamma (the **gun** pipeline). Both the
   experiment and the calibration/measurement page call this **same** function.
   There must be exactly one copy of the color math in the codebase.

The bug happened because two copies of the color math existed and drifted. The
whole point of this design is that they can't.

---

## 2. Non-negotiable constraints (safety rails)

- **Preserve the as-run colors.** Move the existing `ADJUSTED_COLORS_1` and
  `ADJUSTED_COLORS_2` literals **verbatim** into `legacy/as_run_colors.json`
  with a short `legacy/README.md` stating: these define the exact colors shown
  to the first 25 participants (20 on monitor 1, 5 on monitor 2) and are
  required for salvage analysis of that data. Remove their *use* from the render
  path, but never their *content* from the repo.
- **Do not modify** `colorNames.json`, `checkTrials.json`,
  `validationPicked.json`, `validationRandom.json`. They carry identity labels
  and data continuity. If you believe one needs to change, **stop and ask**.
- **Do not touch** the categorization task, its per-monitor PNG folders, or the
  `jspsych/` folder. Out of scope (§7).
- **Do not run git history-rewriting or destructive commands** (no
  `push --force`, no `reset --hard` on shared branches, no branch/tag deletion,
  no `clean -fdx`). New branch, incremental commits, PR/diff for human review.
- **Never invent measured numbers or calibration constants.** Where a real
  measurement is required and not yet available, insert a clearly-marked `TODO`
  and make the load-time self-test **fail loudly**. A plausible-looking fake
  value is worse than a hard failure.
- **Preserve exact numerical behavior** of the gun conversion (§4). These are
  load-bearing and a "cleanup" that changes any of them silently changes the
  stimuli:
  - rounding is JavaScript `Math.round`, i.e. `Math.floor(x + 0.5)`;
  - the gun path uses **absolute** `set_Y` (the ~0–100 scale), **not** `Y/100`;
  - clamp each negative gun percentage to `0`;
  - if any of R/G/B is `< 0` or `> 255`, output black `(0,0,0)`.

---

## 3. Files

### Inputs the human must add to the repo (ask if missing)
- `calibration_monitor_1_near_door.html` — the monitor-1 calibration file. Source
  of monitor-1 primaries, gamma fits, per-color xyY adjustments, global offset,
  and the original xyY targets (`set_xorig/yorig/Yorig`).
- The equivalent **monitor-2** calibration HTML.
- `build_calibration_colors_gun.py` — the reference offline implementation of the
  gun pipeline. Use it as the golden reference for §6 Gate B. Do not depend on it
  at runtime.

### Files you create
```
color/
  uw58_targets.json        # {identityHex: {x,y,Y}}  — 58 entries, no adjustments
  calib_monitor1.json      # monitor-1 manifest (see §5)
  calib_monitor2.json      # monitor-2 manifest
  renderColor.js           # the ONE renderer + gun conversion (no DOM)
  self_test.js             # load-time verification (see §6, Gate C)
  fixtures/
    gun_monitor1.json      # golden {identityHex: "RRGGBB"} from build_calibration_colors_gun.py
    gun_monitor2.json      # same for monitor 2
legacy/
  as_run_colors.json       # the moved ADJUSTED_COLORS_1/_2 literals, verbatim
  README.md
```

### Files you edit
- `index.html` — triplet task only (§4).
- `styles.css` — only if a hardcoded stimulus color exists there; the squares are
  inline-styled, so likely no change. Check and report.

---

## 4. What to change in `index.html` (triplet task only)

1. Load `color/renderColor.js`, `color/uw58_targets.json`, and the manifest for
   the selected monitor (`calib_monitor1.json` / `calib_monitor2.json`), keyed by
   the existing `monitorNum` prompt. Keep `origHexOf(id)` unchanged — it is the
   identity extractor and still works on `img_triplets/XXXXXX.png`.

2. Replace the hex-lookup render path. Today:
   ```js
   function adjustedHex(id) {
       var h = origHexOf(id);
       if (h && ADJUSTED_COLORS.hasOwnProperty(h)) return "#" + ADJUSTED_COLORS[h];
       if (h) return "#" + h;
       return id;
   }
   ```
   Becomes a runtime computation (no precomputed table):
   ```js
   function cssColorFor(id) {
       var h = origHexOf(id);
       var target = TARGETS[h];               // canonical xyY for this identity
       if (!target) return "rgb(0,0,0)";      // unknown id -> black + warn (do not guess)
       var rgb = renderColor(target, CALIB, h);
       return "rgb(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + ")";
   }
   ```
   Point `colorSquare()` and `colorPair()` at `cssColorFor()` instead of
   `adjustedHex()`. The `<div>` sizing/layout stays identical.

3. Delete the `ADJUSTED_COLORS_1` / `ADJUSTED_COLORS_2` literals and the
   `ADJUSTED_COLORS = (monitorNum === 2) ? ... : ...` selection from `index.html`
   **after** their content is saved to `legacy/as_run_colors.json`.

4. **Background color.** Today it's hardcoded (`rgb(95,95,95)` monitor 1,
   `rgb(85,84,92)` monitor 2), and monitor 1's was hand-dialed. Do **not** silently
   recompute it. Store the background as an explicit field in each manifest
   (`background_rgb`) — for the already-characterized monitors, record the current
   as-run value; flag in the manifest whether it is hand-dialed or renderer-derived
   so the human can decide whether to re-measure it. Read `background_rgb` from the
   manifest instead of hardcoding.

5. On every saved data row, add: the selected `monitor`, the manifest's content
   hash, and a boolean `calibration_verified` (from §6). This makes each session
   reconstructable and makes future salvage decisions trivial.

---

## 5. Manifest format (`color/calib_monitorN.json`)

Keyed by **identity hex** so it joins to targets without relying on array order
(the calibration HTML arrays are in "set order"; `colorNames.json` is sorted —
never join by position, always by identity).

```json
{
  "monitor": 1,
  "label": "near_door",
  "provenance": { "measured_by": "", "date": "", "instrument": "",
                  "room": "", "monitor_model": "", "monitor_mode": "",
                  "white_point": "" },
  "primaries": { "xR":0.654,"yR":0.331,"xG":0.332,"yG":0.614,"xB":0.151,"yB":0.067 },
  "gamma": { "constantR":1.6881,"slopeR":0.4599,
             "constantG":1.4456,"slopeG":0.4458,
             "constantB":1.8290,"slopeB":0.4619 },
  "global_offset": { "x":0.0, "y":0.0, "Y":0.0 },
  "adjustments":  { "4DC7E8": {"dx":0.0,"dy":0.0,"dY":-1.98}, "...": {} },
  "background_rgb": [95,95,95],
  "background_hand_dialed": true,
  "expected_rgb": { "4DC7E8": [76,195,228], "...": [] },
  "measured_xyY": { "4DC7E8": {"x":null,"y":null,"Y":null}, "...": {} }
}
```

- `primaries`, `gamma`, `global_offset` come from the calibration HTML (Part 1
  constants, and the trailing constant in the `set_x.push(... )` lines for the
  offset — monitor 1 is `0/0/0`, monitor 2 is `-0.01/-0.02/-1`).
- `adjustments` come from `set_xadj/yadj/Yadj`, re-keyed from set index → identity
  hex via the same identity computation used to build `uw58_targets.json`.
- `expected_rgb` = the gun output for each color; populate from
  `build_calibration_colors_gun.py` (Gate B fixtures). Used by the self-test.
- `measured_xyY` = spectroradiometer readings of the **runtime-rendered** squares.
  Leave `null` until the human measures (see §6 Gate C / §8). Do not fabricate.

---

## 6. Verification gates

Two of these need **no instrument** and must pass before the human is asked to
measure anything.

**Gate A — identity join is exact.** Build `uw58_targets.json` by joining each
calibration-HTML set index (1..58) to its identity hex (the standard-sRGB
encoding of `set_xorig/yorig/Yorig`, the same rule that produced the current
table keys). Assert:
- every key in `uw58_targets.json` appears in `colorNames.json`, and vice versa
  (58/58, black `000000` included, background excluded);
- every identity matches the corresponding `ADJUSTED_COLORS_1` **key** 58/58.
If this fails, the target extraction is wrong — stop and report; do not proceed.

**Gate B — the JS renderer matches the reference gun pipeline.** For monitor 1,
`renderColor(TARGETS[h], calib_monitor1, h)` must equal `fixtures/gun_monitor1.json[h]`
for all 58 identities; same for monitor 2. That golden fixture is the output of
`build_calibration_colors_gun.py`. Passing this proves the runtime JS renderer ==
the Python gun port == the math the calibration HTML actually painted. This is the
regression test that ties the refactor to the already-reviewed offline fix.
- Sanity anchor: the identity `FFFFFF` (target Y≈100) should render to roughly
  `[185,189,183]` (`#B9BDB7`), a muted gray — **not** near-white. If white renders
  near `#FFFFFF`/`#FDFDFD`, the sRGB path is still in play and Gate B is not really
  passing.

**Gate C — self-test against measurement (needs the instrument).** At experiment
load, `self_test.js` recomputes `renderColor` for all 58 colors and asserts they
equal `expected_rgb` exactly; if `measured_xyY` is populated, it also checks that
the recorded achieved xyY is within tolerance of each target. On any mismatch it
**blocks launch** with a visible experimenter-facing error. Until `measured_xyY`
is filled, the self-test should **warn on screen and set `calibration_verified =
false`** rather than fabricate a pass. The corrected wave must not collect data
while `calibration_verified` is false.

---

## 7. Explicitly out of scope

- The **categorization task** and its per-monitor PNG image sets. They also need
  regenerating, but that's a separate job — do not modify them here.
- The **already-collected 25 participants' data** and its analysis/salvage.
- The **embedding pipeline**. It consumes identity labels (hex → integer →
  judgments) and is unaffected by this change. Do not touch it.
- `jspsych/`.

---

## 8. Human-in-the-loop seam (do not automate past this)

`renderColor` is deterministic from primaries + gamma + adjustments, so the
experiment **renders correctly without any new measurement** and Gates A and B
are fully checkable now. What still requires the human and the spectroradiometer:

1. Display the **runtime-rendered** squares (the same `renderColor` under test)
   and measure each color's achieved xyY on each monitor, at the documented
   monitor mode. A tiny optional page that steps through all 58 identities via
   `renderColor` and shows the identity label is the clean way to do this —
   it measures exactly what the study will show, closing the loop the old setup
   left open.
2. Fill `measured_xyY` (and confirm `expected_rgb`) in each manifest; fill
   `provenance`.
3. Confirm Gate C passes → `calibration_verified = true` → corrected wave may run.

Also record, for the environment assumption this all rests on: the study machine
must drive the panel the same way the calibration session did (same monitor mode,
no ICC profile / OS color management in between). Capture `navigator.userAgent`,
screen properties, and fullscreen state on each session, and have the experimenter
confirm monitor + mode at launch.

---

## 9. Suggested commit sequence

1. Branch `color-runtime-refactor`.
2. Add `build_calibration_colors_gun.py` + both calibration HTMLs (human) →
   generate `uw58_targets.json`, `calib_monitor{1,2}.json`, and the gun fixtures →
   Gate A passes. Commit.
3. Add `renderColor.js` + Gate B fixtures/tests → Gate B passes (incl. the white
   sanity anchor). Commit.
4. Move `ADJUSTED_COLORS_*` to `legacy/as_run_colors.json`; wire `index.html`
   triplet render to `cssColorFor`/`renderColor`; move background to manifest.
   Commit.
5. Add `self_test.js` + data-row provenance (`monitor`, manifest hash,
   `calibration_verified`). Commit.
6. Open PR/diff for human review. **Stop here.** Measurement (§8) and any data
   collection happen after human sign-off.

If anything about identity, the item files, or what the prior participants saw is
ambiguous, stop and ask rather than guessing — the cost of a wrong assumption here
is another wave of miscalibrated data.
