#!/usr/bin/env python3
"""
build_manifests.py
------------------------------------------------------------------------------
Offline, one-time build step (not loaded at runtime). Reads the two monitor
calibration HTMLs and produces the JSON the runtime renderer consumes:

  color/uw58_targets.json     canonical {identityHex: {x,y,Y}} targets, no
                               per-monitor adjustments
  color/calib_monitor1.json   monitor-1 manifest (primaries, gamma, offset,
                               per-color adjustments, expected_rgb, ...)
  color/calib_monitor2.json   monitor-2 manifest
  color/fixtures/gun_monitor1.json   golden {identityHex: "RRGGBB"}
  color/fixtures/gun_monitor2.json   golden {identityHex: "RRGGBB"}

The gun-pipeline math is NOT reimplemented here: this script imports
calibration_files/build_calibration_colors_gun.py (the human-reviewed,
already-verified reference implementation) and calls its functions directly,
so the fixtures are byte-for-byte what that script would print. This script
only handles re-keying (set index -> identity hex) and JSON shaping.

Run from the repo root:
    python3 color/build_manifests.py
"""

import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAL_DIR = os.path.join(REPO_ROOT, "calibration_files")
COLOR_DIR = os.path.join(REPO_ROOT, "color")

MONITORS = [
    {"num": 1, "label": "near_door", "file": "calibration_monitor_1_near_door.html",
     "current_background_rgb": [95, 95, 95], "background_hand_dialed": True,
     "background_source": "hand-dialed (not derived from any pipeline)"},
    {"num": 2, "label": "far_door", "file": "calibration_monitor_2_far_door.html",
     "current_background_rgb": [85, 84, 92], "background_hand_dialed": False,
     "background_source": "as-run value was derived via the OLD standard-sRGB "
                           "pipeline (the bug this refactor fixes), not the gun "
                           "pipeline -- flagged for human re-measurement decision"},
]

CALIBRATION_DATE = "2022-09-23"  # from the "//Calibration date: 9-23-22" comment
                                  # in both calibration HTMLs


def xyY_to_srgb_precise(x, y, Y_rel):
    """Identity-key extraction ONLY. Same standard sRGB(D65) pipeline as
    build_calibration_colors_gun.py's xyY_to_srgb, but with the full-precision
    IEC 61966-2-1 matrix instead of that script's 4-decimal-rounded one.

    Gate A showed the rounded matrix reproduces 57/58 existing identity keys
    but flips index 44 (E81A4B -> E81B4B) because its green channel sits at
    26.63 vs 26.50 -- on opposite sides of a rounding boundary. The full
    precision matrix reproduces all 58/58 keys exactly, confirming it is what
    originally produced colorNames.json / ADJUSTED_COLORS_1's keys. This does
    NOT affect the gun-pipeline rendering math (xyY_to_gun / Gate B) at all --
    only how identities are re-derived from the calibration file's original
    xyY values.
    """
    if Y_rel <= 0 or y <= 0:
        return [0, 0, 0]
    X = (x / y) * Y_rel
    Z = ((1 - x - y) / y) * Y_rel
    r = 3.2404542 * X - 1.5371385 * Y_rel - 0.4985314 * Z
    g = -0.9692660 * X + 1.8760108 * Y_rel + 0.0415560 * Z
    b = 0.0556434 * X - 0.2040259 * Y_rel + 1.0572252 * Z

    def srgb_gamma(c):
        return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

    return [round(min(1.0, max(0.0, srgb_gamma(v))) * 255) for v in (r, g, b)]


def identity_hex(gun, x, y, Y_abs):
    return gun.to_hex(xyY_to_srgb_precise(x, y, Y_abs / gun.WHITE_Y))


def load_gun_module():
    path = os.path.join(CAL_DIR, "build_calibration_colors_gun.py")
    spec = importlib.util.spec_from_file_location("build_calibration_colors_gun", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_targets(gun, cal_text_by_monitor):
    """Canonical uw58 targets (no adjustments), asserted identical across
    both calibration files since they share the same set_xorig/yorig/Yorig."""
    targets_by_monitor = {}
    for num, cal_text in cal_text_by_monitor.items():
        xo = gun.parse_array(cal_text, "set_xorig")
        yo = gun.parse_array(cal_text, "set_yorig")
        Lo = gun.parse_array(cal_text, "set_Yorig")
        entries = {}
        for i in range(1, gun.N + 1):
            key = identity_hex(gun, xo[i], yo[i], Lo[i])
            entries[key] = {"x": xo[i], "y": yo[i], "Y": Lo[i]}
        targets_by_monitor[num] = entries

    nums = list(targets_by_monitor.keys())
    ref = targets_by_monitor[nums[0]]
    for num in nums[1:]:
        if targets_by_monitor[num] != ref:
            raise SystemExit(
                "FATAL: canonical uw58 targets differ between monitor calibration "
                "files ({} vs {}). Stop -- the identity/target join is not exact."
                .format(nums[0], num))
    if len(ref) != gun.N:
        raise SystemExit("FATAL: expected {} target entries, got {}".format(gun.N, len(ref)))
    return ref


def build_manifest(gun, cal_text, mon_spec):
    mon = gun.parse_monitor(cal_text)
    xo = gun.parse_array(cal_text, "set_xorig")
    yo = gun.parse_array(cal_text, "set_yorig")
    Lo = gun.parse_array(cal_text, "set_Yorig")
    xa = gun.parse_array(cal_text, "set_xadj")
    ya = gun.parse_array(cal_text, "set_yadj")
    La = gun.parse_array(cal_text, "set_Yadj")

    off_x = gun.detect_offset(cal_text, "set_x", "set_xadj")
    off_y = gun.detect_offset(cal_text, "set_y", "set_yadj")
    off_L = gun.detect_offset(cal_text, "set_Y", "set_Yadj")

    adjustments = {}
    expected_rgb = {}
    measured_xyY = {}
    for i in range(1, gun.N + 1):
        key = identity_hex(gun, xo[i], yo[i], Lo[i])
        adjustments[key] = {"dx": xa[i], "dy": ya[i], "dY": La[i]}
        ax, ay, aL = xo[i] + xa[i] + off_x, yo[i] + ya[i] + off_y, Lo[i] + La[i] + off_L
        rgb = gun.xyY_to_gun(ax, ay, aL, mon)
        if key == "000000":
            rgb = [0, 0, 0]
        expected_rgb[key] = gun.to_hex(rgb)
        measured_xyY[key] = {"x": None, "y": None, "Y": None}

    manifest = {
        "monitor": mon_spec["num"],
        "label": mon_spec["label"],
        "provenance": {
            "measured_by": "",
            "date": CALIBRATION_DATE,
            "instrument": "",
            "room": "",
            "monitor_model": "",
            "monitor_mode": "",
            "white_point": "",
        },
        "primaries": {
            "xR": mon["xR"], "yR": mon["yR"],
            "xG": mon["xG"], "yG": mon["yG"],
            "xB": mon["xB"], "yB": mon["yB"],
        },
        "gamma": {
            "constantR": mon["constantR"], "slopeR": mon["slopeR"],
            "constantG": mon["constantG"], "slopeG": mon["slopeG"],
            "constantB": mon["constantB"], "slopeB": mon["slopeB"],
        },
        "global_offset": {"x": off_x, "y": off_y, "Y": off_L},
        "adjustments": adjustments,
        "background_rgb": mon_spec["current_background_rgb"],
        "background_hand_dialed": mon_spec["background_hand_dialed"],
        "background_source": mon_spec["background_source"],
        "expected_rgb": expected_rgb,
        "measured_xyY": measured_xyY,
        "calibration_verified": False,
    }
    return manifest, expected_rgb


def main():
    gun = load_gun_module()

    cal_text_by_monitor = {}
    for mon_spec in MONITORS:
        path = os.path.join(CAL_DIR, mon_spec["file"])
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            cal_text_by_monitor[mon_spec["num"]] = f.read()

    targets = build_targets(gun, cal_text_by_monitor)

    os.makedirs(os.path.join(COLOR_DIR, "fixtures"), exist_ok=True)
    with open(os.path.join(COLOR_DIR, "uw58_targets.json"), "w") as f:
        json.dump(targets, f, indent=2, sort_keys=True)
        f.write("\n")
    print("wrote color/uw58_targets.json ({} entries)".format(len(targets)))

    for mon_spec in MONITORS:
        cal_text = cal_text_by_monitor[mon_spec["num"]]
        manifest, expected_rgb = build_manifest(gun, cal_text, mon_spec)

        manifest_path = os.path.join(COLOR_DIR, "calib_monitor{}.json".format(mon_spec["num"]))
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
            f.write("\n")
        print("wrote {}".format(os.path.relpath(manifest_path, REPO_ROOT)))

        fixture_path = os.path.join(COLOR_DIR, "fixtures",
                                     "gun_monitor{}.json".format(mon_spec["num"]))
        with open(fixture_path, "w") as f:
            json.dump(expected_rgb, f, indent=2, sort_keys=True)
            f.write("\n")
        print("wrote {}".format(os.path.relpath(fixture_path, REPO_ROOT)))


if __name__ == "__main__":
    main()
