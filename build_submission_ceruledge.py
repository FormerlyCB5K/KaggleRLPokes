"""
build_submission_ceruledge.py — Package the Ceruledge rules-based agent for Kaggle.

Usage:
    python build_submission_ceruledge.py

AFTERWARDS: run

kaggle competitions submit -c pokemon-tcg-ai-battle -f Submissions/CeruledgeChildSecondborn.tar.gz -m "insert comments here!"

kaggle competitions submissions -c pokemon-tcg-ai-battle
"""

import io
import os
import tarfile

# ── EDIT ME ───────────────────────────────────────────────────────────────────
OUTPUT_TAR = "Submissions/Alakazam-Baby-Twooo.tar.gz"
# ─────────────────────────────────────────────────────────────────────────────

with tarfile.open(OUTPUT_TAR, "w:gz") as tar:
    tar.add("Alakazam-Agent/main.py", arcname="main.py")
    tar.add("Alakazam-Agent/deck.csv", arcname="deck.csv")
    for root, dirs, files in os.walk("cg_download"):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for file in files:
            if file.endswith(".pyc"):
                continue
            fpath = os.path.join(root, file)
            tar.add(fpath, arcname=fpath.replace("cg_download", "cg", 1))

print(f"Built {OUTPUT_TAR}")
