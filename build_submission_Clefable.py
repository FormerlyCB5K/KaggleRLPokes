"""
build_submission.py — Bake evolved weights into main.py and package for Kaggle.

Usage:
    python build_submission.py

Edit the two variables below before running.



AFTERWARDS: run

kaggle competitions submit -c pokemon-tcg-ai-battle -f Submissions/submission-v3NAMEOFSUBMISSION.tar.gz -m "insert comments here!"

kaggle competitions submissions -c pokemon-tcg-ai-battle


"""

import io
import json
import os
import re
import tarfile

# ── EDIT ME ───────────────────────────────────────────────────────────────────
WEIGHTS_FILE = "Evo-V2\evo-output\gen_142_weights.json"   # path to best weights JSON
OUTPUT_TAR   = "Submissions/Clefable-v5.tar.gz"             # name of the output tarball
# ─────────────────────────────────────────────────────────────────────────────

with open(WEIGHTS_FILE) as f:
    weights = json.load(f)["weights"]

with open("Clefable-Agent/main.py", encoding="utf-8") as f:
    src = f.read()

for name, val in weights.items():
    src = re.sub(
        r'^(' + re.escape(name) + r'\s*=\s*)([^\n]+)$',
        lambda m, v=val: f'{m.group(1)}{v!r}',
        src, flags=re.MULTILINE
    )

with tarfile.open(OUTPUT_TAR, "w:gz") as tar:
    data = src.encode("utf-8")
    info = tarfile.TarInfo(name="main.py")
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))
    tar.add("Clefable-Agent/deck.csv", arcname="deck.csv")
    for root, dirs, files in os.walk("cg_download"):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for file in files:
            if file.endswith(".pyc"):
                continue
            fpath = os.path.join(root, file)
            tar.add(fpath, arcname=fpath.replace("cg_download", "cg", 1))

print(f"Built {OUTPUT_TAR}")
print(f"  weights source: {WEIGHTS_FILE}")
print(f"  sample — W_PRIZE_DIFF = {weights.get('W_PRIZE_DIFF', '?')}")
