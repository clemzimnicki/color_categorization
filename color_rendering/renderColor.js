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
// renderColor(target, calib, identity, options)
//   target   {x, y, Y}            canonical xyY for this identity (color_rendering/uw58_targets.json).
//                                  Y is the ABSOLUTE ~0-100 scale, not Y/100.
//   calib    monitor manifest     primaries, gamma, global_offset, adjustments (color_rendering/calib_monitorN.json)
//   identity 6-hex string         key into calib.adjustments
//   options  {clampToGamut}       optional. Selects the out-of-gamut policy --
//                                 see the two return shapes below.
//
// Default (no options, or options.clampToGamut falsy -- the triplet task and
// the self-test/gate scripts use this): returns [R, G, B] each 0-255, or
// [0,0,0] if any channel falls outside [0,255] ("black-out" policy).
//
// options.clampToGamut === true (the categorization task uses this): returns
// { rgb: [R,G,B], inGamut: bool, rawRgb: [R,G,B] } where rgb is each raw
// channel clamped to [0,255] then rounded (never black just for being
// out-of-range), inGamut is false if any raw channel fell outside [0,255],
// and rawRgb is the unclamped, unrounded drive values for logging.
//
// Both policies share the same gun-conversion math (xyYToRawGunRGB) -- there
// must be exactly one copy of it.
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

    // The one copy of the xyY -> gun-RGB math. Returns raw (unclamped,
    // unrounded) drive values plus whether all three landed in [0,255];
    // callers decide what to do with an out-of-gamut result.
    function xyYToRawGunRGB(x, y, Yabs, primaries, gamma) {
        if (Yabs <= 0) return { R: 0, G: 0, B: 0, inGamut: false };

        var xR = primaries.xR, yR = primaries.yR;
        var xG = primaries.xG, yG = primaries.yG;
        var xB = primaries.xB, yB = primaries.yB;

        var step2 = (xG - xB) * (yR - yB) - (yG - yB) * (xR - xB);
        if (step2 === 0) return { R: 0, G: 0, B: 0, inGamut: false };
        var step1 = (x - xB) * (yR - yB) - (y - yB) * (xR - xB);
        var step3 = step1 / step2;
        var step4 = ((x - xB) - step3 * (xG - xB)) / (xR - xB);
        var step5 = 1.0 - step3 - step4;
        var step6 = step4 * yR + step3 * yG + step5 * yB;
        if (step6 === 0) return { R: 0, G: 0, B: 0, inGamut: false };

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

        var inGamut = R >= 0 && R <= 255 && G >= 0 && G <= 255 && B >= 0 && B <= 255;
        return { R: R, G: G, B: B, inGamut: inGamut };
    }

    // Black-out policy (triplet task, self-test, gate scripts): exact-range
    // drive values only, else [0,0,0].
    function xyYToGunRGB(x, y, Yabs, primaries, gamma) {
        var raw = xyYToRawGunRGB(x, y, Yabs, primaries, gamma);
        if (!raw.inGamut) return [0, 0, 0];
        return [jsRound(raw.R), jsRound(raw.G), jsRound(raw.B)];
    }

    function clampChannel(v) {
        if (v < 0) return 0;
        if (v > 255) return 255;
        return v;
    }

    function renderColor(target, calib, identity, options) {
        var adj = (calib.adjustments && calib.adjustments[identity]) || { dx: 0, dy: 0, dY: 0 };
        var off = calib.global_offset || { x: 0, y: 0, Y: 0 };

        var x = target.x + adj.dx + off.x;
        var y = target.y + adj.dy + off.y;
        var Yabs = target.Y + adj.dY + off.Y; // absolute scale -- NOT /100

        if (options && options.clampToGamut) {
            var raw = xyYToRawGunRGB(x, y, Yabs, calib.primaries, calib.gamma);
            return {
                rgb: [
                    jsRound(clampChannel(raw.R)),
                    jsRound(clampChannel(raw.G)),
                    jsRound(clampChannel(raw.B))
                ],
                inGamut: raw.inGamut,
                rawRgb: [raw.R, raw.G, raw.B]
            };
        }

        return xyYToGunRGB(x, y, Yabs, calib.primaries, calib.gamma);
    }

    renderColor._xyYToGunRGB = xyYToGunRGB; // exposed for tests only
    return renderColor;
});
