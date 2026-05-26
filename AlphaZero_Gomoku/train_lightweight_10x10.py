# -*- coding: utf-8 -*-
"""Train the lightweight 10x10 Gomoku policy-value model by self-play."""

from __future__ import print_function

import argparse
import copy
import json
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np

from game import Board
from lightweight_policy_value_10x10 import LightweightPolicyValueNet
from mcts_alphaZero import MCTSPlayer


REPO_ROOT = Path(__file__).resolve().parent


class RandomPlayer(object):
    def __init__(self):
        self.player = None

    def set_player_ind(self, p):
        self.player = p

    def get_action(self, board):
        return random.choice(board.availables)


class TacticalPlayer(object):
    def __init__(self, model):
        self.model = model
        self.player = None

    def set_player_ind(self, p):
        self.player = p

    def get_action(self, board):
        opponent = self.model.opponent_of(board, self.player)
        for move in board.availables:
            if self.model.would_win(board, move, self.player):
                return move
        for move in board.availables:
            if self.model.would_win(board, move, opponent):
                return move
        return max(board.availables, key=lambda move: self.model.action_features(board, move, self.player).dot(self.model.action_weights))


def play_match(width, height, n_in_row, p1, p2, start_player):
    board = Board(width=width, height=height, n_in_row=n_in_row)
    board.init_board(start_player)
    p1.set_player_ind(board.players[0])
    p2.set_player_ind(board.players[1])
    players = {board.players[0]: p1, board.players[1]: p2}
    while True:
        current = board.get_current_player()
        move = players[current].get_action(board)
        board.do_move(move)
        end, winner = board.game_end()
        if end:
            return int(winner), len(board.states)


def evaluate(model, games=8, playouts=40):
    width = height = 10
    n_in_row = 5
    output = {}
    for opponent_name in ("random", "tactical"):
        results = []
        for i in range(games):
            ai = MCTSPlayer(model.policy_value_fn, c_puct=5, n_playout=playouts)
            opponent = RandomPlayer() if opponent_name == "random" else TacticalPlayer(model)
            winner, moves = play_match(width, height, n_in_row, ai, opponent, start_player=i % 2)
            results.append({"winner": winner, "moves": moves, "start_player": i % 2})
        counts = Counter(r["winner"] for r in results)
        output[opponent_name] = {
            "games": games,
            "ai_wins": counts[1],
            "opponent_wins": counts[2],
            "ties": counts[-1],
            "score": round((counts[1] + 0.5 * counts[-1]) / games, 3),
            "avg_moves": round(sum(r["moves"] for r in results) / games, 2),
        }
    return output


def self_play_game(model, playouts=25, temp=1.0, max_moves=100):
    board = Board(width=10, height=10, n_in_row=5)
    board.init_board(start_player=0)
    player = MCTSPlayer(model.policy_value_fn, c_puct=5, n_playout=playouts, is_selfplay=1)
    states = []
    probs = []
    players = []
    while True:
        states.append(copy.deepcopy(board))
        players.append(board.current_player)
        move, move_probs = player.get_action(board, temp=temp, return_prob=1)
        probs.append(move_probs.copy())
        board.do_move(move)
        end, winner = board.game_end()
        if end or len(board.states) >= max_moves:
            if not end:
                winner = -1
            samples = []
            for state, target, current_player in zip(states, probs, players):
                if winner == -1:
                    z = 0.0
                else:
                    z = 1.0 if current_player == winner else -1.0
                samples.append((state, target, z))
            return int(winner), len(board.states), samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=28)
    parser.add_argument("--playouts", type=int, default=24)
    parser.add_argument("--eval-games", type=int, default=8)
    parser.add_argument("--eval-playouts", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--model-out", type=Path, default=REPO_ROOT / "models" / "lightweight_policy_10x10.json")
    parser.add_argument("--log-out", type=Path, default=REPO_ROOT / "experiments" / "training_log_10x10.json")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    model = LightweightPolicyValueNet(board_width=10, board_height=10, n_in_row=5)

    started_at = time.perf_counter()
    before_eval = evaluate(model, games=args.eval_games, playouts=args.eval_playouts)
    log = {
        "config": {
            "board": "10x10",
            "n_in_row": 5,
            "self_play_games": args.games,
            "self_play_playouts": args.playouts,
            "eval_games": args.eval_games,
            "eval_playouts": args.eval_playouts,
            "seed": args.seed,
        },
        "before_eval": before_eval,
        "games": [],
    }
    data_buffer = []
    for i in range(args.games):
        winner, moves, samples = self_play_game(model, playouts=args.playouts, temp=1.0)
        data_buffer.extend(samples)
        if len(data_buffer) > 500:
            data_buffer = data_buffer[-500:]
        metrics = model.update_batch(data_buffer, lr=0.10, value_lr=0.04)
        entry = {
            "game": i + 1,
            "winner": winner,
            "moves": moves,
            "samples": len(samples),
            "buffer": len(data_buffer),
            "policy_loss": round(metrics["policy_loss"], 4),
            "value_loss": round(metrics["value_loss"], 4),
        }
        log["games"].append(entry)
        print(json.dumps(entry, ensure_ascii=False))

    after_eval = evaluate(model, games=args.eval_games, playouts=args.eval_playouts)
    log["after_eval"] = after_eval
    log["elapsed_sec"] = round(time.perf_counter() - started_at, 3)
    log["model_out"] = str(args.model_out)
    log["final_action_weights"] = [round(float(x), 4) for x in model.action_weights]
    log["final_value_weights"] = [round(float(x), 4) for x in model.value_weights]
    model.save_model(args.model_out)
    args.log_out.parent.mkdir(parents=True, exist_ok=True)
    args.log_out.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"saved_model": str(args.model_out), "log": str(args.log_out), "after_eval": after_eval}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
