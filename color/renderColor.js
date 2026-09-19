// renderColor.js
// ------------------------------------------------------------------------
// THE ONE renderer. Maps a canonical CIE xyY target + a monitor's measured
// gun characterization -> device RGB. No DOM access, so it can be loaded
// both in the browser (triplet task, calibration/measurement page) and in
// Node (Gate B tests). This is a faithful port of Part 3 of the monitor
// calibration HTML (calibration_files/calibration_monitor_*.html) and of
// build_calibration_colors_gun.py's xyY_to_gun -- there must be exactly one
// copy of this math in the codebase.
//
// renderColor(target, calib, identity)
//   target   {x, y, Y}            canonical xyY for this identity (color/uw58_targets.json).
//                                  Y is the ABSOLUTE ~0-100 scale, not Y/100.
//   calib    monitor manifest     primaries, gamma, global_offset, adjustments (color/calib_monitorN.json)
//   identity 6-hex string         key into calib.adjustments
// returns [R, G, B] each 0-255 (or [0,0,0] if out of gamut / out of range).
// ------------------------------------------------------------------------
(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.renderColor = factory();
    }
})(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    // JavaScript Math.round, i.e. floor(x + 0.5). Load-bearing: do not swap
    // in a "cleaner" rounding function -- see COLOR_REFACTOR_BRIEF.md §2.
    function jsRound(v) {
        return Math.floor(v + 0.5);
    }

    function xyYToGunRGB(x, y, Yabs, primaries, gamma) {
        if (Yabs <= 0) return [0, 0, 0];

        var xR = primaries.xR, yR = primaries.yR;
        var xG = primaries.xG, yG = primaries.yG;
        var xB = primaries.xB, yB = primaries.yB;

        var step2 = (xG - xB) * (yR - yB) - (yG - yB) * (xR - xB);
        if (step2 === 0) return [0, 0, 0];
        var step1 = (x - xB) * (yR - yB) - (y - yB) * (xR - xB);
        var step3 = step1 / step2;
        var step4 = ((x - xB) - step3 * (xG - xB)) / (xR - xB);
        var step5 = 1.0 - step3 - step4;
        var step6 = step4 * yR + step3 * yG + step5 * yB;
        if (step6 === 0) return [0, 0, 0];

        var gR = (step4 * yR) / step6;
        var gG = (step3 * yG) / step6;
        var gB = 1.0 - gR - gG;

        // Out-of-gamut chromaticity -> clamp each negative gun percentage to 0.
        if (gR < 0.0) gR = 0.0;
        if (gG < 0.0) gG = 0.0;
        if (gB < 0.0) gB = 0.0;

        var R = Math.pow(10.0, gamma.constantR) * Math.pow(gR * Yabs, gamma.slopeR);
        var G = Math.pow(10.0, gamma.constantG) * Math.pow(gG * Yabs, gamma.slopeG);
        var B = Math.pow(10.0, gamma.constantB) * Math.pow(gB * Yabs, gamma.slopeB);

        // Out-of-range drive value -> black.
        if (R < 0 || R > 255 || G < 0 || G > 255 || B < 0 || B > 255) {
            return [0, 0, 0];
        }
        return [jsRound(R), jsRound(G), jsRound(B)];
    }

    function renderColor(target, calib, identity) {
        var adj = (calib.adjustments && calib.adjustments[identity]) || { dx: 0, dy: 0, dY: 0 };
        var off = calib.global_offset || { x: 0, y: 0, Y: 0 };

        var x = target.x + adj.dx + off.x;
        var y = target.y + adj.dy + off.y;
        var Yabs = target.Y + adj.dY + off.Y; // absolute scale -- NOT /100

        return xyYToGunRGB(x, y, Yabs, calib.primaries, calib.gamma);
    }

    renderColor._xyYToGunRGB = xyYToGunRGB; // exposed for tests only
    return renderColor;
});
