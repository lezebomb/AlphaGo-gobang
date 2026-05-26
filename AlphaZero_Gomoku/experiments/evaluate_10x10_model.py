# -*- coding: utf-8 -*-
"""Evaluate the trained 10x10 lightweight Gomoku model."""

from __future__ import print_function

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from game import Board  # noqa: E402
from lightweight_policy_value_10x10 import LightweightPolicyValueNet  # noqa: E402
from mcts_alphaZero import MCTSPlayer  # noqa: E402
from train_lightweight_10x10 import RandomPlayer, TacticalPlayer, play_match  # noqa: E402


def json_default(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    raise TypeError("Object of type {} is not JSON serializable".format(obj.__class__.__name__))


def evaluate(model, games, ai_playouts, opponent_name):
    results = []
    for i in range(games):
        ai = MCTSPlayer(model.policy_value_fn, c_puct=5, n_playout=ai_playouts)
        opponent = RandomPlayer() if opponent_name == "random" else TacticalPlayer(model)
        started = time.perf_counter()
        winner, moves = play_match(10, 10, 5, ai, opponent, start_player=i % 2)
        elapsed = time.perf_counter() - started
        results.append(
            {
                "winner": int(winner),
                "moves": int(moves),
                "elapsed_sec": round(elapsed, 3),
                "start_player": i % 2,
            }
        )
    counts = Counter(r["winner"] for r in results)
    first = [r for r in results if r["start_player"] == 0]
    second = [r for r in results if r["start_player"] == 1]

    def score(subset):
        if not subset:
            return None
        c = Counter(r["winner"] for r in subset)
        return round((c[1] + 0.5 * c[-1]) / len(subset), 3)

    return {
        "summary": {
            "games": games,
            "ai_wins": counts[1],
            "opponent_wins": counts[2],
            "ties": counts[-1],
            "score": round((counts[1] + 0.5 * counts[-1]) / games, 3),
            "score_first": score(first),
            "score_second": score(second),
            "avg_moves": round(sum(r["moves"] for r in results) / games, 2),
            "avg_elapsed_sec": round(sum(r["elapsed_sec"] for r in results) / games, 3),
            "avg_sec_per_move": round(sum(r["elapsed_sec"] / max(1, r["moves"]) for r in results) / games, 3),
        },
        "games": results,
    }


def first_move_probe(model, playouts):
    board = Board(width=10, height=10, n_in_row=5)
    board.init_board(start_player=0)
    ai = MCTSPlayer(model.policy_value_fn, c_puct=5, n_playout=playouts)
    move, move_probs = ai.get_action(board, temp=1e-3, return_prob=1)
    top = np.argsort(move_probs)[::-1][:6]
    return {
        "selected_move": int(move),
        "selected_display_location": [int(10 - (move // 10)), int(move % 10 + 1)],
        "top": [
            {
                "move": int(idx),
                "display_location": [10 - (int(idx) // 10), int(idx) % 10 + 1],
                "prob": round(float(move_probs[idx]), 4),
            }
            for idx in top
            if move_probs[idx] > 0
        ],
    }


def playout_sweep(model, games, playouts):
    settings = []
    for playout in playouts:
        result = evaluate(model, games, playout, "tactical")
        settings.append({"playouts": playout, "summary": result["summary"]})
    return settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--sweep-games", type=int, default=4)
    parser.add_argument("--playouts", type=int, default=80)
    parser.add_argument("--sweep", type=str, default="30,60,100")
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--model-file", type=Path, default=REPO_ROOT / "models" / "lightweight_policy_10x10.json")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "experiments" / "results_10x10.json")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    model = LightweightPolicyValueNet(model_file=args.model_file)
    output = {
        "config": {
            "board": "10x10",
            "n_in_row": 5,
            "model_file": args.model_file.name,
            "playouts": args.playouts,
            "seed": args.seed,
        },
        "first_move_probe": first_move_probe(model, args.playouts),
        "matches": {
            "ai_vs_random": evaluate(model, args.games, args.playouts, "random"),
            "ai_vs_tactical": evaluate(model, args.games, args.playouts, "tactical"),
        },
        "playout_sweep": playout_sweep(
            model,
            args.sweep_games,
            [int(x.strip()) for x in args.sweep.split(",") if x.strip()],
        ),
    }
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2, default=json_default))


if __name__ == "__main__":
    main()
