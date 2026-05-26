# -*- coding: utf-8 -*-
"""A small trainable policy-value model for 10x10 Gomoku.

This model is intentionally lightweight so it can be trained and demonstrated
on a normal classroom machine without PyTorch/TensorFlow. It is not a CNN, but
it follows the AlphaZero interface: ``policy_value_fn(board)`` returns action
priors and a leaf value, and the priors can be improved by MCTS self-play.
"""

from __future__ import print_function

import json
from pathlib import Path

import numpy as np


ACTION_FEATURES = [
    "win_now",
    "block_win",
    "own_line",
    "opp_line",
    "own_open",
    "opp_open",
    "own_four",
    "opp_four",
    "own_three",
    "opp_three",
    "nearby",
    "center",
]

VALUE_FEATURES = [
    "own_best_line",
    "opp_best_line",
    "own_four_count",
    "opp_four_count",
    "own_three_count",
    "opp_three_count",
    "stone_diff",
    "center_control",
]


def stable_softmax(scores):
    scores = np.asarray(scores, dtype=np.float64)
    scores = scores - np.max(scores)
    exps = np.exp(scores)
    total = np.sum(exps)
    if total <= 0:
        return np.ones_like(scores) / len(scores)
    return exps / total


class LightweightPolicyValueNet(object):
    def __init__(self, board_width=10, board_height=10, n_in_row=5, model_file=None):
        self.board_width = int(board_width)
        self.board_height = int(board_height)
        self.n_in_row = int(n_in_row)
        self.action_weights = np.array(
            [8.0, 7.2, 2.0, 1.7, 0.9, 0.8, 4.8, 4.4, 2.1, 1.9, 0.35, 0.8],
            dtype=np.float64,
        )
        self.value_weights = np.array(
            [1.5, -1.5, 2.8, -2.8, 1.2, -1.2, 0.25, 0.35],
            dtype=np.float64,
        )
        self.bias = 0.0
        self.value_bias = 0.0
        if model_file:
            self.load_model(model_file)

    def save_model(self, model_file):
        path = Path(model_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "board_width": self.board_width,
            "board_height": self.board_height,
            "n_in_row": self.n_in_row,
            "action_features": ACTION_FEATURES,
            "value_features": VALUE_FEATURES,
            "action_weights": self.action_weights.tolist(),
            "value_weights": self.value_weights.tolist(),
            "bias": float(self.bias),
            "value_bias": float(self.value_bias),
            "note": "Lightweight self-play-trained Gomoku policy-value model.",
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_model(self, model_file):
        payload = json.loads(Path(model_file).read_text(encoding="utf-8"))
        self.board_width = int(payload["board_width"])
        self.board_height = int(payload["board_height"])
        self.n_in_row = int(payload["n_in_row"])
        self.action_weights = np.array(payload["action_weights"], dtype=np.float64)
        self.value_weights = np.array(payload["value_weights"], dtype=np.float64)
        self.bias = float(payload.get("bias", 0.0))
        self.value_bias = float(payload.get("value_bias", 0.0))

    def opponent_of(self, board, player):
        return board.players[0] if player == board.players[1] else board.players[1]

    def move_location(self, board, move):
        row = move // board.width
        col = move % board.width
        return row, col

    def line_info(self, board, move, player):
        row, col = self.move_location(board, move)
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
        best_len = 1
        best_open = 0
        line_scores = []
        for dr, dc in directions:
            length = 1
            open_ends = 0
            for sign in (1, -1):
                r = row + sign * dr
                c = col + sign * dc
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
            if length > best_len:
                best_len = length
                best_open = open_ends
            elif length == best_len and open_ends > best_open:
                best_open = open_ends
            line_scores.append((length, open_ends))
        best_open = max(open_ends for length, open_ends in line_scores if length == best_len)
        return best_len, best_open, line_scores

    def would_win(self, board, move, player):
        if move not in board.availables:
            return False
        original = board.states.get(move)
        was_available = move in board.availables
        board.states[move] = player
        if was_available:
            board.availables.remove(move)
        win, winner = board.has_a_winner()
        if was_available:
            board.availables.append(move)
            board.availables.sort()
        if original is None:
            del board.states[move]
        else:
            board.states[move] = original
        return bool(win and winner == player)

    def nearby_count(self, board, move):
        row, col = self.move_location(board, move)
        count = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                r, c = row + dr, col + dc
                if 0 <= r < board.height and 0 <= c < board.width:
                    loc = board.location_to_move([r, c])
                    if loc in board.states:
                        count += 1
        return count / 8.0

    def center_score(self, board, move):
        row, col = self.move_location(board, move)
        center_r = (board.height - 1) / 2.0
        center_c = (board.width - 1) / 2.0
        max_dist = center_r + center_c
        dist = abs(row - center_r) + abs(col - center_c)
        return 1.0 - dist / max_dist if max_dist else 1.0

    def action_features(self, board, move, player=None):
        player = board.current_player if player is None else player
        opp = self.opponent_of(board, player)
        own_len, own_open, own_lines = self.line_info(board, move, player)
        opp_len, opp_open, opp_lines = self.line_info(board, move, opp)
        own_four = sum(1 for length, open_ends in own_lines if length >= self.n_in_row - 1 and open_ends > 0)
        opp_four = sum(1 for length, open_ends in opp_lines if length >= self.n_in_row - 1 and open_ends > 0)
        own_three = sum(1 for length, open_ends in own_lines if length >= self.n_in_row - 2 and open_ends == 2)
        opp_three = sum(1 for length, open_ends in opp_lines if length >= self.n_in_row - 2 and open_ends == 2)
        return np.array(
            [
                1.0 if self.would_win(board, move, player) else 0.0,
                1.0 if self.would_win(board, move, opp) else 0.0,
                own_len / float(self.n_in_row),
                opp_len / float(self.n_in_row),
                own_open / 2.0,
                opp_open / 2.0,
                min(own_four, 2) / 2.0,
                min(opp_four, 2) / 2.0,
                min(own_three, 2) / 2.0,
                min(opp_three, 2) / 2.0,
                self.nearby_count(board, move),
                self.center_score(board, move),
            ],
            dtype=np.float64,
        )

    def legal_feature_matrix(self, board):
        moves = list(board.availables)
        if not moves:
            return moves, np.zeros((0, len(ACTION_FEATURES)), dtype=np.float64)
        features = np.vstack([self.action_features(board, move) for move in moves])
        return moves, features

    def board_value_features(self, board):
        player = board.current_player
        opp = self.opponent_of(board, player)
        own_best = 0
        opp_best = 0
        own_four = 0
        opp_four = 0
        own_three = 0
        opp_three = 0
        for move in board.availables:
            own_len, own_open, own_lines = self.line_info(board, move, player)
            opp_len, opp_open, opp_lines = self.line_info(board, move, opp)
            own_best = max(own_best, own_len)
            opp_best = max(opp_best, opp_len)
            own_four += sum(1 for length, open_ends in own_lines if length >= self.n_in_row - 1 and open_ends > 0)
            opp_four += sum(1 for length, open_ends in opp_lines if length >= self.n_in_row - 1 and open_ends > 0)
            own_three += sum(1 for length, open_ends in own_lines if length >= self.n_in_row - 2 and open_ends == 2)
            opp_three += sum(1 for length, open_ends in opp_lines if length >= self.n_in_row - 2 and open_ends == 2)
        own_stones = sum(1 for p in board.states.values() if p == player)
        opp_stones = sum(1 for p in board.states.values() if p == opp)
        center_control = 0.0
        for move, p in board.states.items():
            sign = 1.0 if p == player else -1.0
            center_control += sign * self.center_score(board, move)
        scale = max(1.0, len(board.states))
        return np.array(
            [
                own_best / float(self.n_in_row),
                opp_best / float(self.n_in_row),
                min(own_four, 5) / 5.0,
                min(opp_four, 5) / 5.0,
                min(own_three, 5) / 5.0,
                min(opp_three, 5) / 5.0,
                (own_stones - opp_stones) / scale,
                center_control / scale,
            ],
            dtype=np.float64,
        )

    def policy_value_fn(self, board):
        legal_moves, features = self.legal_feature_matrix(board)
        if not legal_moves:
            return [], 0.0
        scores = features.dot(self.action_weights) + self.bias
        probs = stable_softmax(scores)
        value_features = self.board_value_features(board)
        value = np.tanh(value_features.dot(self.value_weights) + self.value_bias)
        return zip(legal_moves, probs), float(value)

    def update_batch(self, samples, lr=0.08, value_lr=0.04, l2=1e-4):
        if not samples:
            return {"policy_loss": 0.0, "value_loss": 0.0}
        grad_w = np.zeros_like(self.action_weights)
        grad_b = 0.0
        grad_v = np.zeros_like(self.value_weights)
        grad_vb = 0.0
        policy_losses = []
        value_losses = []
        used = 0
        for sample in samples:
            board, target_probs, winner_z = sample
            legal_moves, features = self.legal_feature_matrix(board)
            if not legal_moves:
                continue
            target = np.array([target_probs[m] for m in legal_moves], dtype=np.float64)
            total = np.sum(target)
            if total <= 0:
                continue
            target /= total
            logits = features.dot(self.action_weights) + self.bias
            probs = stable_softmax(logits)
            diff = probs - target
            grad_w += features.T.dot(diff)
            grad_b += np.sum(diff)
            policy_losses.append(float(-np.sum(target * np.log(probs + 1e-10))))

            vf = self.board_value_features(board)
            pred = np.tanh(vf.dot(self.value_weights) + self.value_bias)
            err = pred - winner_z
            local_grad = 2.0 * err * (1.0 - pred * pred)
            grad_v += local_grad * vf
            grad_vb += local_grad
            value_losses.append(float(err * err))
            used += 1
        if used:
            self.action_weights -= lr * (grad_w / used + l2 * self.action_weights)
            self.bias -= lr * grad_b / used
            self.value_weights -= value_lr * (grad_v / used + l2 * self.value_weights)
            self.value_bias -= value_lr * grad_vb / used
        return {
            "policy_loss": float(np.mean(policy_losses)) if policy_losses else 0.0,
            "value_loss": float(np.mean(value_losses)) if value_losses else 0.0,
            "samples": used,
        }
