# -*- coding: utf-8 -*-
"""Reproducible experiments for the AlphaZero_Gomoku report.

The script keeps the original repository untouched and uses the provided
Theano/Lasagne weights through the pure NumPy inference path.
"""

from __future__ import print_function

import argparse
import json
import pickle
import random
import sys
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from game import Board, Game  # noqa: E402
from mcts_alphaZero import MCTSPlayer as AlphaZeroMCTSPlayer  # noqa: E402
from mcts_pure import MCTSPlayer as PureMCTSPlayer  # noqa: E402
from policy_value_net_numpy import PolicyValueNetNumpy  # noqa: E402


class RandomPlayer(object):
    def __init__(self):
        self.player = None

    def set_player_ind(self, p):
        self.player = p

    def get_action(self, board):
        return random.choice(board.availables)

    def __str__(self):
        return "Random {}".format(self.player)


class HeuristicPlayer(object):
    """A deterministic tactical baseline for Gomoku.

    Priority:
    1. win immediately if possible;
    2. block the opponent's immediate win;
    3. maximize local line length with a small center preference.
    """

    def __init__(self):
        self.player = None

    def set_player_ind(self, p):
        self.player = p

    def _opponent(self, board):
        return board.players[0] if self.player == board.players[1] else board.players[1]

    @staticmethod
    def _would_win(board, move, player):
        board_copy = deepcopy(board)
        board_copy.current_player = player
        board_copy.do_move(move)
        win, winner = board_copy.has_a_winner()
        return win and winner == player

    @staticmethod
    def _line_score(board, move, player):
        row, col = board.move_to_location(move)
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
        total = 0.0
        for dr, dc in directions:
            length = 1
            open_ends = 0
            for sign in (1, -1):
                r, c = row + sign * dr, col + sign * dc
                while 0 <= r < board.height and 0 <= c < board.width:
                    loc = board.location_to_move([r, c])
                    occupant = board.states.get(loc)
                    if occupant == player:
                        length += 1
                        r += sign * dr
                        c += sign * dc
                    else:
                        if occupant is None:
                            open_ends += 1
                        break
            total += (length ** 2) * (1 + 0.25 * open_ends)
        center = (board.width - 1) / 2.0
        center_bonus = 1.0 / (1.0 + abs(row - center) + abs(col - center))
        return total + center_bonus

    def get_action(self, board):
        opponent = self._opponent(board)
        for move in board.availables:
            if self._would_win(board, move, self.player):
                return move
        for move in board.availables:
            if self._would_win(board, move, opponent):
                return move
        return max(board.availables, key=lambda m: self._line_score(board, m, self.player))

    def __str__(self):
        return "Heuristic {}".format(self.player)


def load_numpy_policy(width, height, model_file):
    with open(model_file, "rb") as f:
        try:
            policy_param = pickle.load(f)
        except UnicodeDecodeError:
            f.seek(0)
            policy_param = pickle.load(f, encoding="bytes")
    return PolicyValueNetNumpy(width, height, policy_param)


def play_game(width, height, n_in_row, player1, player2, start_player=0):
    board = Board(width=width, height=height, n_in_row=n_in_row)
    board.init_board(start_player)
    p1, p2 = board.players
    player1.set_player_ind(p1)
    player2.set_player_ind(p2)
    players = {p1: player1, p2: player2}
    transcript = []
    started_at = time.perf_counter()
    while True:
        current_player = board.get_current_player()
        player = players[current_player]
        move = player.get_action(board)
        board.do_move(move)
        transcript.append(
            {
                "player": int(current_player),
                "move": int(move),
                "location": board.move_to_location(int(move)),
            }
        )
        end, winner = board.game_end()
        if end:
            break
    elapsed = time.perf_counter() - started_at
    return {
        "winner": int(winner),
        "moves": len(board.states),
        "elapsed_sec": round(elapsed, 3),
        "transcript": transcript,
    }


def run_match(width, height, n_in_row, policy, games, alpha_playouts, opponent, opponent_playouts):
    results = []
    for i in range(games):
        alpha = AlphaZeroMCTSPlayer(policy.policy_value_fn, c_puct=5, n_playout=alpha_playouts)
        if opponent == "random":
            other = RandomPlayer()
        elif opponent == "heuristic":
            other = HeuristicPlayer()
        elif opponent == "pure_mcts":
            other = PureMCTSPlayer(c_puct=5, n_playout=opponent_playouts)
        else:
            raise ValueError("unsupported opponent: {}".format(opponent))
        result = play_game(
            width,
            height,
            n_in_row,
            alpha,
            other,
            start_player=i % 2,
        )
        result["start_player"] = i % 2
        results.append(result)
    return results


def summarize_match(results):
    winner_counts = Counter(r["winner"] for r in results)
    games = len(results)
    alpha_first = [r for r in results if r["start_player"] == 0]
    alpha_second = [r for r in results if r["start_player"] == 1]

    def score(subset):
        if not subset:
            return None
        counts = Counter(r["winner"] for r in subset)
        return round((counts[1] + 0.5 * counts[-1]) / len(subset), 3)

    return {
        "games": games,
        "alpha_wins": winner_counts[1],
        "opponent_wins": winner_counts[2],
        "ties": winner_counts[-1],
        "alpha_score": round((winner_counts[1] + 0.5 * winner_counts[-1]) / games, 3),
        "alpha_score_first": score(alpha_first),
        "alpha_score_second": score(alpha_second),
        "avg_moves": round(sum(r["moves"] for r in results) / games, 2),
        "avg_elapsed_sec": round(sum(r["elapsed_sec"] for r in results) / games, 3),
        "avg_sec_per_move": round(
            sum(r["elapsed_sec"] / max(1, r["moves"]) for r in results) / games,
            3,
        ),
    }


def first_move_probe(width, height, n_in_row, policy, alpha_playouts):
    board = Board(width=width, height=height, n_in_row=n_in_row)
    board.init_board(start_player=0)
    alpha = AlphaZeroMCTSPlayer(policy.policy_value_fn, c_puct=5, n_playout=alpha_playouts)
    move, move_probs = alpha.get_action(board, temp=1e-3, return_prob=1)
    top_indices = np.argsort(move_probs)[::-1][:5]
    return {
        "selected_move": int(move),
        "selected_location": board.move_to_location(int(move)),
        "top5": [
            {
                "move": int(idx),
                "location": board.move_to_location(int(idx)),
                "prob": round(float(move_probs[idx]), 4),
            }
            for idx in top_indices
            if move_probs[idx] > 0
        ],
    }


def self_play_probe(width, height, n_in_row, policy, alpha_playouts):
    board = Board(width=width, height=height, n_in_row=n_in_row)
    game = Game(board)
    player = AlphaZeroMCTSPlayer(
        policy.policy_value_fn,
        c_puct=5,
        n_playout=alpha_playouts,
        is_selfplay=1,
    )
    started_at = time.perf_counter()
    winner, play_data = game.start_self_play(player, is_shown=0, temp=1.0)
    play_data = list(play_data)
    elapsed = time.perf_counter() - started_at
    return {
        "winner": int(winner),
        "raw_samples": len(play_data),
        "augmented_samples_if_training": len(play_data) * 8,
        "moves": len(board.states),
        "elapsed_sec": round(elapsed, 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=12)
    parser.add_argument("--pure-games", type=int, default=6)
    parser.add_argument("--alpha-playouts", type=int, default=120)
    parser.add_argument("--pure-playouts", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20260521)
    parser.add_argument("--board-size", type=int, default=8)
    parser.add_argument("--n-in-row", type=int, default=5)
    parser.add_argument("--model-file", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "experiments" / "results_8x8.json")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    width, height, n_in_row = args.board_size, args.board_size, args.n_in_row
    model_file = args.model_file or REPO_ROOT / "best_policy_8_8_5.model"
    policy = load_numpy_policy(width, height, model_file)

    random_results = run_match(
        width,
        height,
        n_in_row,
        policy,
        args.games,
        args.alpha_playouts,
        opponent="random",
        opponent_playouts=0,
    )
    heuristic_results = run_match(
        width,
        height,
        n_in_row,
        policy,
        args.games,
        args.alpha_playouts,
        opponent="heuristic",
        opponent_playouts=0,
    )
    pure_mcts_results = run_match(
        width,
        height,
        n_in_row,
        policy,
        args.pure_games,
        args.alpha_playouts,
        opponent="pure_mcts",
        opponent_playouts=args.pure_playouts,
    )
    output = {
        "config": {
            "board": "{}x{}".format(width, height),
            "n_in_row": n_in_row,
            "model_file": str(model_file.name),
            "alpha_playouts": args.alpha_playouts,
            "pure_mcts_playouts": args.pure_playouts,
            "seed": args.seed,
        },
        "first_move_probe": first_move_probe(width, height, n_in_row, policy, args.alpha_playouts),
        "self_play_probe": self_play_probe(width, height, n_in_row, policy, args.alpha_playouts),
        "matches": {
            "alpha_vs_random": {
                "summary": summarize_match(random_results),
                "sample_game": random_results[0],
            },
            "alpha_vs_heuristic": {
                "summary": summarize_match(heuristic_results),
                "sample_game": heuristic_results[0],
            },
            "alpha_vs_pure_mcts": {
                "summary": summarize_match(pure_mcts_results),
                "sample_game": pure_mcts_results[0],
            },
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
