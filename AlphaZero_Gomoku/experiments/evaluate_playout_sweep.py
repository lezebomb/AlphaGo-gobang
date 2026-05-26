# -*- coding: utf-8 -*-
"""Evaluate 8x8 AlphaZero-Gomoku with different MCTS playout budgets."""

from __future__ import print_function

import argparse
import json
import random
from pathlib import Path

import numpy as np

from run_gomoku_experiment import load_numpy_policy, run_match, summarize_match


REPO_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=6)
    parser.add_argument("--playouts", type=str, default="40,80,120,200")
    parser.add_argument("--seed", type=int, default=20260521)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "experiments" / "playout_sweep_8x8.json")
    args = parser.parse_args()

    width = height = 8
    n_in_row = 5
    model_file = REPO_ROOT / "best_policy_8_8_5.model"
    policy = load_numpy_policy(width, height, model_file)

    output = {
        "config": {
            "board": "8x8",
            "n_in_row": n_in_row,
            "model_file": model_file.name,
            "games_per_setting": args.games,
            "seed": args.seed,
            "opponent": "heuristic",
        },
        "settings": [],
    }
    for playouts in [int(p.strip()) for p in args.playouts.split(",") if p.strip()]:
        random.seed(args.seed + playouts)
        np.random.seed(args.seed + playouts)
        results = run_match(
            width,
            height,
            n_in_row,
            policy,
            args.games,
            alpha_playouts=playouts,
            opponent="heuristic",
            opponent_playouts=0,
        )
        output["settings"].append(
            {
                "alpha_playouts": playouts,
                "summary": summarize_match(results),
            }
        )

    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
