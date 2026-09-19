#!/usr/bin/env python3
"""Execute the submission notebook after reading secrets without echoing them."""

from __future__ import annotations

import getpass
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = PROJECT_ROOT / "maritime_SQL_agent_colab_submission.ipynb"


def set_secret(name: str, required: bool = True) -> None:
    value = getpass.getpass(f"{name}: ")
    if value:
        os.environ[name] = value
    elif required:
        raise SystemExit(f"{name} is required")


def main() -> None:
    set_secret("NEON_DSN")
    set_secret("OPENAI_API_KEY")
    set_secret("LANGSMITH_API_KEY", required=False)

    nb = nbformat.read(NOTEBOOK_PATH, as_version=4)
    client = NotebookClient(
        nb,
        timeout=1800,
        kernel_name="python3",
        resources={"metadata": {"path": str(PROJECT_ROOT)}},
        allow_errors=False,
    )
    client.execute()
    nbformat.write(nb, NOTEBOOK_PATH)
    print(f"Executed and saved: {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()

