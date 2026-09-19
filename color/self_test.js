// self_test.js
// ------------------------------------------------------------------------
// Gate C: load-time verification that renderColor() matches what the
// manifest says the monitor should produce, and (once measured) that the
// physical monitor actually produced it. No DOM access here -- the caller
// (index.html) decides how to surface a failure on screen.
//
// runColorSelfTest(renderColor, targets, calib) -> {
//   ok:                 boolean  false only on a hard mismatch (fatal)
//   fatal:              boolean  true  -> caller MUST block launch
//   calibrationVerified boolean  true only once expected_rgb matches AND
//                                every identity's measured_xyY is within
//                                tolerance of its (adjusted) target
//   messages:           string[] human-readable detail, first line is the summary
// }
//
// This never fabricates a pass: until calib.measured_xyY is filled in for
// every identity, calibrationVerified is false (a warning, not a block).
// ------------------------------------------------------------------------
(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.runColorSelfTest = factory();
    }
})(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    // TODO(human): these tolerances are placeholders. Set them from the
    // spectroradiometer's actual repeatability/accuracy once §8 measurement
    // is done; until then they only gate the (currently unreachable, since
    // measured_xyY is null) branch below.
    var XY_TOLERANCE = 0.01;
    var Y_TOLERANCE = 2.0;

    function toHex(rgb) {
        return rgb.map(function (v) {
            return ("0" + v.toString(16).toUpperCase()).slice(-2);
        }).join("");
    }

    function runColorSelfTest(renderColor, targets, calib) {
        var identities = Object.keys(targets);

        // ---- expected_rgb: renderColor() must reproduce it exactly -------
        var mismatches = [];
        identities.forEach(function (id) {
            var got = toHex(renderColor(targets[id], calib, id));
            var want = calib.expected_rgb && calib.expected_rgb[id];
            if (!want || got !== String(want).toUpperCase()) {
                mismatches.push(id + ": renderColor=" + got + " expected_rgb=" + want);
            }
        });
        if (mismatches.length > 0) {
            return {
                ok: false,
                fatal: true,
                calibrationVerified: false,
                messages: [
                    "renderColor() does not match calib_monitor" + calib.monitor +
                    ".json expected_rgb for " + mismatches.length + " / " +
                    identities.length + " color(s):"
                ].concat(mismatches)
            };
        }

        // ---- measured_xyY: needs the human + spectroradiometer (§8) ------
        var measured = calib.measured_xyY || {};
        var isMeasured = function (id) {
            var m = measured[id];
            return m && m.x !== null && m.x !== undefined &&
                m.y !== null && m.y !== undefined &&
                m.Y !== null && m.Y !== undefined;
        };
        var haveAllMeasurements = identities.every(isMeasured);

        if (!haveAllMeasurements) {
            return {
                ok: true,
                fatal: false,
                calibrationVerified: false,
                messages: [
                    "calib_monitor" + calib.monitor + ".json has no (or incomplete) " +
                    "spectroradiometer measurements (measured_xyY). renderColor() matches " +
                    "the expected gun-pipeline output, but the physical monitor output has " +
                    "not been verified. calibration_verified = false -- this session's data " +
                    "must not be treated as the corrected/verified wave."
                ]
            };
        }

        // ---- measured_xyY vs (adjusted) target, within tolerance ---------
        var outOfTolerance = [];
        identities.forEach(function (id) {
            var t = targets[id];
            var adj = (calib.adjustments && calib.adjustments[id]) || { dx: 0, dy: 0, dY: 0 };
            var off = calib.global_offset || { x: 0, y: 0, Y: 0 };
            var wantX = t.x + adj.dx + off.x;
            var wantY = t.y + adj.dy + off.y;
            var wantYabs = t.Y + adj.dY + off.Y;
            var m = measured[id];
            if (Math.abs(m.x - wantX) > XY_TOLERANCE ||
                Math.abs(m.y - wantY) > XY_TOLERANCE ||
                Math.abs(m.Y - wantYabs) > Y_TOLERANCE) {
                outOfTolerance.push(
                    id + ": measured=(" + m.x + "," + m.y + "," + m.Y + ") target=(" +
                    wantX.toFixed(4) + "," + wantY.toFixed(4) + "," + wantYabs.toFixed(2) + ")"
                );
            }
        });
        if (outOfTolerance.length > 0) {
            return {
                ok: false,
                fatal: true,
                calibrationVerified: false,
                messages: [
                    "Measured xyY is outside tolerance (xy=±" + XY_TOLERANCE +
                    ", Y=±" + Y_TOLERANCE + ") for " + outOfTolerance.length + " / " +
                    identities.length + " color(s):"
                ].concat(outOfTolerance)
            };
        }

        return {
            ok: true,
            fatal: false,
            calibrationVerified: true,
            messages: [
                "Gate C passed: expected_rgb matches and measured_xyY is within " +
                "tolerance for all " + identities.length + " colors."
            ]
        };
    }

    return runColorSelfTest;
});
