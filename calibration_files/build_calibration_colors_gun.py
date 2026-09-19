#!/usr/bin/env python3
"""
build_calibration_colors_gun.py
------------------------------------------------------------------------------
Corrected build for the monitor-calibration -> experiment color tables.

WHY THIS DIFFERS FROM build_calibration_colors.py
--------------------------------------------------
The spectroradiometer only ever measured what the calibration HTML actually
painted, and that HTML paints the GUN-pipeline drive values:
    rgb(Rval, Gval, Bval)
where Rval/Gval/Bval come from the barycentric solve against the monitor's
measured primaries (xR,yR,...) and the per-gun luminance fits
(constantR/slopeR,...). You iterated set_*adj until the *measured* xyY hit the
target -- i.e. you found the predistortion that makes the GUN pipeline land on
target on that panel.

The old build then threw the gun pipeline away and re-encoded the adjusted xyY
through the STANDARD sRGB pipeline (xyY->XYZ->linear sRGB(D65)->gamma->hex).
Those sRGB hex codes are DIFFERENT numbers than the gun drive values you
measured, so painting them raw sends the monitor light you never validated.

This script instead makes the experiment TABLE VALUE = the gun drive values for
the adjusted xyY -- exactly the integers the calibration HTML computed and the
spectroradiometer signed off on.

WHAT STAYS THE SAME
-------------------
- KEYS remain the STANDARD-pipeline hex of the *original* (unadjusted) xyY.
  They're only identifiers the experiment looks colors up by (origHexOf ->
  ADJUSTED_COLORS[h]); they must keep matching your existing stimulus IDs, so
  the sRGB conversion is the right one for the key and must not change.
- Only the VALUES change: standard-sRGB-of-adjusted  ->  gun-of-adjusted.

TWO EASY-TO-MISS DETAILS (both handled below)
---------------------------------------------
1. The gun pipeline uses the ABSOLUTE set_Y (the ~0..100 "CIE Y * 116" scale in
   the HTML), NOT Y/100. The sRGB key path DOES normalize by 100. Don't cross
   them.
2. The HTML rounds with JavaScript Math.round == floor(x + 0.5). Python's
   round() is banker's rounding and can differ at .5, which would make your
   study values disagree with the measured integers by 1 level. The gun path
   here uses floor(x + 0.5) to match the HTML exactly. (Keys keep Python round
   so they reproduce your existing table byte-for-byte.)

USAGE
-----
  # print the corrected table (keys unchanged, values = gun drive values)
  python build_calibration_colors_gun.py calibration_monitor_1_near_door.html --monitor 1

  # THE COMPARISON YOU WANTED: current ADJUSTED_COLORS_1 vs what it should be
  python build_calibration_colors_gun.py calibration_monitor_1_near_door.html \
         --monitor 1 --compare index.html

  # also dump the corrected map as JSON
  python build_calibration_colors_gun.py calibration_monitor_1_near_door.html \
         --monitor 1 --json

Standard library only.
------------------------------------------------------------------------------
"""

import argparse
import json
import math
import re
import sys

N = 58          # UW58 colors: set indices 1..58; index 0 = background
WHITE_Y = 100   # set_Yorig of the white point -> normalizes Y to [0,1] for sRGB


# ------------------------------------------------------------------ parsing ---
def parse_array(text, name):
    """Extract the numeric JS array assigned to `name` (handles '.3127', '-.03')."""
    m = re.search(re.escape(name) + r"\s*=\s*\[([^\]]*)\]", text)
    if not m:
        raise ValueError("array not found: " + name)
    return [float(tok.strip()) for tok in m.group(1).split(",") if tok.strip() != ""]


def parse_scalar(text, name):
    """Read `name = <number>` (first assignment). Stops before any // comment,
    so 'xR  = .654//0.667' correctly yields 0.654."""
    m = re.search(r"(?<![\w])" + re.escape(name) + r"\s*=\s*([+-]?(?:\d+\.?\d*|\.\d+))",
                  text)
    if not m:
        raise ValueError("scalar not found: " + name)
    return float(m.group(1))


def parse_monitor(text):
    """Pull the monitor-native gun chromaticities + luminance fits from the
    calibration HTML (the values in 'Part 1')."""
    keys = ["constantR", "slopeR", "constantG", "slopeG", "constantB", "slopeB",
            "xR", "yR", "xG", "yG", "xB", "yB"]
    return {k: parse_scalar(text, k) for k in keys}


def detect_offset(text, axis_var, adj_var):
    """Trailing constant in e.g. set_x.push(set_xorig[j] + set_xadj[j] - 0.01)."""
    pat = (re.escape(axis_var) + r"\.push\(\s*\w+\[j\]\s*\+\s*"
           + re.escape(adj_var) + r"\[j\]\s*([+\-]\s*[0-9.]+)?\s*\)")
    m = re.search(pat, text)
    if not m or not m.group(1):
        return 0.0
    return float(m.group(1).replace(" ", ""))


# ------------------------------------------------------- color conversions ---
def js_round(v):
    """JavaScript Math.round: floor(x + 0.5). Matches the calibration HTML."""
    return int(math.floor(v + 0.5))


def srgb_gamma(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def xyY_to_srgb(x, y, Y_rel):
    """STANDARD pipeline. x,y chromaticity; Y_rel is CIE Y in [0,1] (white=1).
    Used for KEYS (original color identifiers). Python round() to reproduce the
    existing table exactly."""
    if Y_rel <= 0 or y <= 0:
        return [0, 0, 0]
    X = (x / y) * Y_rel
    Z = ((1 - x - y) / y) * Y_rel
    r = 3.2406 * X - 1.5372 * Y_rel - 0.4986 * Z
    g = -0.9689 * X + 1.8758 * Y_rel + 0.0415 * Z
    b = 0.0557 * X - 0.2040 * Y_rel + 1.0570 * Z
    return [round(min(1.0, max(0.0, srgb_gamma(v))) * 255) for v in (r, g, b)]


def xyY_to_gun(x, y, Y_abs, mon):
    """GUN pipeline, a faithful port of Part 3 of the calibration HTML.
    x,y chromaticity; Y_abs is the ABSOLUTE set_Y value (NOT /100). Returns the
    8-bit drive values the monitor was actually sent (and measured) for this
    xyY. Rounding matches JS Math.round."""
    if Y_abs <= 0:                       # degenerate / black
        return [0, 0, 0]
    xR, yR = mon["xR"], mon["yR"]
    xG, yG = mon["xG"], mon["yG"]
    xB, yB = mon["xB"], mon["yB"]

    step2 = (xG - xB) * (yR - yB) - (yG - yB) * (xR - xB)
    if step2 == 0:
        return [0, 0, 0]
    step1 = (x - xB) * (yR - yB) - (y - yB) * (xR - xB)
    step3 = step1 / step2
    step4 = ((x - xB) - step3 * (xG - xB)) / (xR - xB)
    step5 = 1.0 - step3 - step4
    step6 = step4 * yR + step3 * yG + step5 * yB
    if step6 == 0:
        return [0, 0, 0]

    gR = (step4 * yR) / step6
    gG = (step3 * yG) / step6
    gB = 1.0 - gR - gG
    # out-of-gamut chromaticity -> clamp gun percentage to 0 (as in the HTML)
    gR = max(gR, 0.0)
    gG = max(gG, 0.0)
    gB = max(gB, 0.0)

    R = (10.0 ** mon["constantR"]) * ((gR * Y_abs) ** mon["slopeR"])
    G = (10.0 ** mon["constantG"]) * ((gG * Y_abs) ** mon["slopeG"])
    B = (10.0 ** mon["constantB"]) * ((gB * Y_abs) ** mon["slopeB"])

    # out-of-range drive value -> black (as in the HTML)
    if R < 0 or R > 255 or G < 0 or G > 255 or B < 0 or B > 255:
        return [0, 0, 0]
    return [js_round(R), js_round(G), js_round(B)]


def to_hex(rgb):
    return "".join("{:02X}".format(v) for v in rgb)


# ------------------------------------------------------------------- build ---
def build(cal_text):
    xo = parse_array(cal_text, "set_xorig")
    yo = parse_array(cal_text, "set_yorig")
    Lo = parse_array(cal_text, "set_Yorig")
    xa = parse_array(cal_text, "set_xadj")
    ya = parse_array(cal_text, "set_yadj")
    La = parse_array(cal_text, "set_Yadj")
    mon = parse_monitor(cal_text)

    off_x = detect_offset(cal_text, "set_x", "set_xadj")
    off_y = detect_offset(cal_text, "set_y", "set_yadj")
    off_L = detect_offset(cal_text, "set_Y", "set_Yadj")

    def adj_xyY(i):
        return (xo[i] + xa[i] + off_x,
                yo[i] + ya[i] + off_y,
                Lo[i] + La[i] + off_L)          # absolute Y (not /100)

    entries = []   # (key, correct_value, current_value_srgb)
    for i in range(1, N + 1):
        key = to_hex(xyY_to_srgb(xo[i], yo[i], Lo[i] / WHITE_Y))

        ax, ay, aL = adj_xyY(i)
        correct = to_hex(xyY_to_gun(ax, ay, aL, mon))              # <-- the fix
        current = to_hex(xyY_to_srgb(ax, ay, aL / WHITE_Y))        # what the old build makes

        if key == "000000":            # keep black pinned, as the old build did
            correct = "000000"
            current = "000000"
        entries.append((key, correct, current))

    # backgrounds (index 0). Gun value is the calibrated one; note that the
    # experiment currently hard-codes a hand-dialed background for monitor 1.
    bx, by, bL = adj_xyY(0)
    bg_gun = xyY_to_gun(bx, by, bL, mon)
    bg_srgb = xyY_to_srgb(bx, by, bL / WHITE_Y)

    return entries, (bg_gun, bg_srgb), (off_x, off_y, off_L), mon


# ---------------------------------------------------------------- emitters ---
def emit_table(entries, monitor):
    lines = ["    var ADJUSTED_COLORS_{} = {{".format(monitor)]
    for i, (k, correct, _cur) in enumerate(entries):
        comma = "," if i < len(entries) - 1 else ""
        lines.append('        "{}": "{}"{}'.format(k, correct, comma))
    lines.append("    };")
    return "\n".join(lines)


def parse_existing(index_text, monitor):
    """Parse ADJUSTED_COLORS_<monitor> from the experiment file, IN ORDER."""
    m = re.search(r"var ADJUSTED_COLORS_" + re.escape(str(monitor))
                  + r"\s*=\s*\{(.*?)\};", index_text, re.S)
    if not m:
        return None
    return [(a.upper(), b.upper()) for a, b in
            re.findall(r'"([0-9A-Fa-f]{6})"\s*:\s*"([0-9A-Fa-f]{6})"', m.group(1))]


def hex_to_rgb(h):
    return [int(h[j:j + 2], 16) for j in (0, 2, 4)]


def compare(entries, current_pairs, monitor):
    """Diff CURRENT table values against the CORRECT (gun) values, per color.
    `current_pairs` is the parsed ADJUSTED_COLORS_<monitor> if available, else
    None (in which case the recomputed sRGB value is used as 'current')."""
    out = []
    out.append("  #  key(orig)   current   ->  SHOULD BE   dR   dG   dB")
    out.append("  -- ---------   -------      ---------   ---  ---  ---")
    n_diff = 0
    max_ch = 0
    sum_ch = 0
    count_ch = 0
    for i, (key, correct, cur_srgb) in enumerate(entries):
        if current_pairs is not None and i < len(current_pairs):
            ck, current = current_pairs[i]
            key_note = "" if ck == key else "  (key mismatch: table={})".format(ck)
        else:
            current = cur_srgb
            key_note = ""
        cr, cg, cb = hex_to_rgb(current)
        rr, rg, rb = hex_to_rgb(correct)
        dR, dG, dB = rr - cr, rg - cg, rb - cb
        differ = (current != correct)
        if differ:
            n_diff += 1
        for d in (abs(dR), abs(dG), abs(dB)):
            max_ch = max(max_ch, d)
            sum_ch += d
            count_ch += 1
        flag = "" if not differ else "  <-- differs"
        out.append("  {:>2} {:>9}   {:>7}  ->  {:>9}   {:>3}  {:>3}  {:>3}{}{}".format(
            i + 1, key, current, correct, dR, dG, dB, flag, key_note))
    mean_ch = (sum_ch / count_ch) if count_ch else 0.0
    out.append("")
    out.append("  {}/{} colors differ between current and corrected".format(n_diff, N))
    out.append("  max single-channel error: {} levels   mean |error|: {:.2f} levels"
               .format(max_ch, mean_ch))
    return "\n".join(out)


# -------------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser(
        description="Build the CORRECTED (gun-pipeline) ADJUSTED_COLORS table and/or "
                    "compare it against the current one.")
    ap.add_argument("calibration_file", help="the Index-monitorCalib-yourColors HTML")
    ap.add_argument("--monitor", default="1", help="monitor label for the variable name")
    ap.add_argument("--compare", metavar="INDEX_HTML",
                    help="diff the current ADJUSTED_COLORS_<monitor> in this file "
                         "against the corrected values")
    ap.add_argument("--json", action="store_true",
                    help="also write adjusted_<monitor>_gun.json")
    ap.add_argument("--no-table", action="store_true",
                    help="skip printing the corrected table (useful with --compare)")
    args = ap.parse_args()

    with open(args.calibration_file, "r", encoding="utf-8", errors="replace") as f:
        cal_text = f.read()

    entries, (bg_gun, bg_srgb), offset, mon = build(cal_text)
    n_changed = sum(1 for k, correct, _ in entries if correct != k)

    print("# source: {}".format(args.calibration_file), file=sys.stderr)
    print("# monitor primaries: R({:.3f},{:.3f}) G({:.3f},{:.3f}) B({:.3f},{:.3f})"
          .format(mon["xR"], mon["yR"], mon["xG"], mon["yG"], mon["xB"], mon["yB"]),
          file=sys.stderr)
    print("# detected global offset (x,y,Y): {}, {}, {}".format(*offset), file=sys.stderr)
    print("# {}/{} corrected values differ from the original UW58 key hex"
          .format(n_changed, N), file=sys.stderr)
    print("# corrected background (gun)  = rgb({},{},{})".format(*bg_gun), file=sys.stderr)
    print("# background if left as sRGB  = rgb({},{},{})".format(*bg_srgb), file=sys.stderr)

    if not args.no_table:
        print(emit_table(entries, args.monitor))
        print()
        print("    // calibrated background for monitor {} (gun pipeline, index 0)"
              .format(args.monitor))
        print("    // rgb({},{},{})".format(*bg_gun))
        print()

    if args.compare:
        with open(args.compare, "r", encoding="utf-8", errors="replace") as f:
            current_pairs = parse_existing(f.read(), args.monitor)
        if current_pairs is None:
            print("[compare] ADJUSTED_COLORS_{} not found in {}"
                  .format(args.monitor, args.compare), file=sys.stderr)
        else:
            if len(current_pairs) != N:
                print("[compare] note: table has {} entries, expected {}"
                      .format(len(current_pairs), N), file=sys.stderr)
            print("# ---- CURRENT vs CORRECTED (monitor {}) ----".format(args.monitor))
            print(compare(entries, current_pairs, args.monitor))

    if args.json:
        out = "adjusted_{}_gun.json".format(args.monitor)
        with open(out, "w") as f:
            json.dump({"offset": list(offset),
                       "background_gun": bg_gun,
                       "entries": [{"key": k, "value": v} for k, v, _ in entries]},
                      f, indent=2)
        print("# wrote {}".format(out), file=sys.stderr)


if __name__ == "__main__":
    main()
