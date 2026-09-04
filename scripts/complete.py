#!/usr/bin/env python3
"""Remove one pending file after the Agent has finished the final note."""

import argparse
from pathlib import Path


CONFIG_DIR = Path.home() / ".config/video-transcript"
PENDING_DIR = CONFIG_DIR / "pending"


def remove_pending_after_success(pending_path, final_path):
    pending_path = Path(pending_path).expanduser().resolve()
    final_path = Path(final_path).expanduser()
    pending_root = PENDING_DIR.expanduser().resolve()
    try:
        pending_path.relative_to(pending_root)
    except ValueError:
        raise ValueError("pending file must be inside the configured pending directory")
    if not pending_path.is_file():
        raise ValueError("pending file does not exist")
    if not final_path.is_file():
        raise ValueError("final note must exist and be non-empty before cleanup")
    if not final_path.read_text(encoding="utf-8").strip():
        raise ValueError("final note must exist and be non-empty before cleanup")
    pending_path.unlink()
    return pending_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pending", required=True)
    parser.add_argument("--final", required=True)
    args = parser.parse_args()
    removed = remove_pending_after_success(args.pending, args.final)
    print(f"PENDING_REMOVED={removed}")


if __name__ == "__main__":
    main()
