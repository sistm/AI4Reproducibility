"""Main Python analysis pipeline."""
import os
from pathlib import Path

import numpy as np


def main():
    data_path = Path("data") / "input.csv"
    out_path = os.path.join("outputs", "figure_1.pdf")
    print(f"Reading {data_path}, writing {out_path}")
    rng = np.random.default_rng(seed=123)
    sample = rng.normal(size=10)
    print(sample.mean())


if __name__ == "__main__":
    main()