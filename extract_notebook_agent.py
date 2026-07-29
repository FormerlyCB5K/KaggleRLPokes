"""Extract ``%%writefile`` agent-package cells from a Jupyter notebook.

This is intentionally small and generic: it turns notebook-authored submission
files into an ordinary folder that can be imported, tested, and versioned.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Sequence


def extract(notebook_path: Path, output_dir: Path) -> list[Path]:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    generated: list[Path] = []

    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        first_line, separator, body = source.partition("\n")
        if not first_line.strip().startswith("%%writefile "):
            continue
        if not separator:
            raise RuntimeError(f"writefile cell has no body: {first_line!r}")
        declared_path = first_line.strip().split(maxsplit=1)[1]
        filename = PurePosixPath(declared_path).name
        if not filename or filename in {".", ".."}:
            raise RuntimeError(f"unsafe writefile path: {declared_path!r}")
        target = output_dir / filename
        if target in generated:
            raise RuntimeError(f"duplicate generated filename: {filename}")
        normalized = body.replace("\r\n", "\n").replace("\r", "\n")
        target.write_text(normalized, encoding="utf-8", newline="\n")
        generated.append(target)

    if not generated:
        raise RuntimeError(f"no %%writefile cells found in {notebook_path}")
    return generated


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("output_dir", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    generated = extract(args.notebook.resolve(), args.output_dir.resolve())
    for path in generated:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
