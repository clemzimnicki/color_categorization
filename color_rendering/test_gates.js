#!/usr/bin/env node
// Gate A/B verification, run with: node color_rendering/test_gates.js
// Gate A (identity join) is checked in Python at build time (build_manifests.py
// asserts it and fails loudly); this script re-checks 58/58 coverage as a
// cheap redundant check, then runs Gate B: renderColor() vs the golden
// gun-pipeline fixtures, for both monitors.
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const renderColor = require("./renderColor.js");

function readJSON(p) {
    return JSON.parse(fs.readFileSync(p, "utf8"));
}

function toHex(rgb) {
    return rgb.map((v) => v.toString(16).toUpperCase().padStart(2, "0")).join("");
}

let failures = 0;

// ---- Gate A: 58/58 identity coverage -------------------------------------
const targets = readJSON(path.join(ROOT, "color_rendering", "uw58_targets.json"));
const targetKeys = Object.keys(targets);
if (targetKeys.length !== 58) {
    console.error(`GATE A FAIL: expected 58 targets, found ${targetKeys.length}`);
    failures++;
} else {
    console.log("GATE A: 58/58 targets present.");
}

// ---- Gate B: renderColor() vs golden gun-pipeline fixtures ----------------
for (const monitor of [1, 2]) {
    const calib = readJSON(path.join(ROOT, "color_rendering", `calib_monitor${monitor}.json`));
    const fixture = readJSON(path.join(ROOT, "color_rendering", "fixtures", `gun_monitor${monitor}.json`));

    let mismatches = 0;
    for (const identity of targetKeys) {
        const rgb = renderColor(targets[identity], calib, identity);
        const got = toHex(rgb);
        const want = fixture[identity];
        if (got !== want) {
            console.error(`  monitor ${monitor} ${identity}: renderColor=${got} fixture=${want}`);
            mismatches++;
        }
    }
    if (mismatches === 0) {
        console.log(`GATE B: monitor ${monitor} — 58/58 match golden gun fixture.`);
    } else {
        console.error(`GATE B FAIL: monitor ${monitor} — ${mismatches}/58 mismatches.`);
        failures++;
    }

    // Sanity anchor: white should render as a muted gray, not near-white.
    const white = renderColor(targets["FFFFFF"], calib, "FFFFFF");
    const isNearWhite = white[0] > 240 && white[1] > 240 && white[2] > 240;
    console.log(`  sanity: monitor ${monitor} FFFFFF -> rgb(${white.join(",")}) ` +
        (isNearWhite ? "-- FAIL: looks near-white, sRGB path may still be in play" : "(muted gray, ok)"));
    if (isNearWhite) failures++;
}

if (failures > 0) {
    console.error(`\n${failures} gate check(s) FAILED.`);
    process.exit(1);
} else {
    console.log("\nAll gate checks PASSED.");
}
