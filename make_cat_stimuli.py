#!/usr/bin/env python3
"""
Regenerate the jsPsych category-stimulus manifests from the PNGs that are
actually sitting in the image folders.

Run it from your experiment root (the folder that contains img_cat/ and
img_cat_unambiguous/):

    python3 make_cat_stimuli.py

It writes categoryStimuli.js and unambiguousCatStimuli.js next to the script.
Re-running is safe; it just overwrites them with whatever is in the folders.

Ordering matches the original files: numeric by color number (color1, color2,
... color10, not color1, color10, color2), then by the rest of the name, which
naturally puts the grid samples first and the *_center_* file last.
"""

import os
import re
import glob

# (image folder, JS variable name, output .js filename)
JOBS = [
    ("img_cat",             "categoryStims",      "categoryStimuli.js"),
    ("img_cat_unambiguous", "unambiguousCatStims", "unambiguousCatStimuli.js"),
]


def sort_key(rel_path):
    """Numeric by colorN, then alphabetical on the remainder."""
    name = os.path.basename(rel_path)
    m = re.search(r"color(\d+)_", name)
    num = int(m.group(1)) if m else 10**9   # unmatched names sort to the end
    return (num, name)


def build_manifest(folder, varname, outfile):
    if not os.path.isdir(folder):
        print(f"  !! folder not found: {folder}/  (skipped)")
        return

    # case-insensitive .png match, de-duplicated
    files = set(glob.glob(os.path.join(folder, "*.png")))
    files |= set(glob.glob(os.path.join(folder, "*.PNG")))

    # store forward-slash relative paths exactly as jsPsych expects them
    rel = sorted((f"{folder}/{os.path.basename(f)}" for f in files), key=sort_key)

    unmatched = [p for p in rel if not re.search(r"color\d+_", os.path.basename(p))]
    if unmatched:
        print(f"  note: {len(unmatched)} file(s) in {folder}/ don't match "
              f"'colorN_' and were appended at the end:")
        for u in unmatched:
            print(f"        {u}")

    lines = ",\n".join(f'  "{p}"' for p in rel)
    js = f"var {varname} = [\n{lines}\n];\n"

    with open(outfile, "w") as fh:
        fh.write(js)
    print(f"  wrote {outfile}: {len(rel)} images")


def main():
    for folder, varname, outfile in JOBS:
        print(f"{folder}/ -> {outfile}")
        build_manifest(folder, varname, outfile)


if __name__ == "__main__":
    main()
