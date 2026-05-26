# -*- coding: utf-8 -*-
"""Play against the provided 8x8 AlphaZero-Gomoku model in the terminal."""

from __future__ import print_function

import argparse
import pickle
import sys
from pathlib import Path

from game import Board
from mcts_alphaZero import MCTSPlayer
from policy_value_net_numpy import PolicyValueNetNumpy


REPO_ROOT = Path(__file__).resolve().parent


class UserQuit(Exception):
    pass


def load_policy(width, height, model_file):
    with open(model_file, "rb") as f:
        try:
            policy_param = pickle.load(f)
        except UnicodeDecodeError:
            f.seek(0)
            policy_param = pickle.load(f, encoding="bytes")
    return PolicyValueNetNumpy(width, height, policy_param)


def display_to_internal(board, display_row, display_col):
    row = board.height - display_row
    col = display_col - 1
    return row, col


def internal_to_display(board, move):
    row, col = board.move_to_location(move)
    return board.height - row, col + 1


def render_board(board, human_player):
    cell = 4
    prefix = "     "
    print()
    print(prefix + "".join("{:>{w}}".format(c, w=cell) for c in range(1, board.width + 1)))
    print(prefix + "-" * (cell * board.width))
    for display_row in range(1, board.height + 1):
        cells = []
        for display_col in range(1, board.width + 1):
            row, col = display_to_internal(board, display_row, display_col)
            move = board.location_to_move([row, col])
            piece = board.states.get(move)
            if piece is None:
                symbol = "."
            elif piece == human_player:
                symbol = "X"
            else:
                symbol = "O"
            cells.append("{:>{w}}".format(symbol, w=cell))
        print("{:>3} |{}".format(display_row, "".join(cells)))
    print()
    print("X=你, O=AI。输入：行,列，例如 3,4；hint 获取建议；q 退出。")


def ask_human_move(board, policy, hint_playouts):
    while True:
        raw = input("你的落子: ").strip().lower()
        if raw in ("q", "quit", "exit"):
            raise UserQuit
        if raw == "hint":
            hint_player = MCTSPlayer(policy.policy_value_fn, c_puct=5, n_playout=hint_playouts)
            move = hint_player.get_action(board)
            print("建议落子: {},{}".format(*internal_to_display(board, move)))
            continue
        try:
            row_text, col_text = raw.replace("，", ",").split(",")
            display_row, display_col = int(row_text), int(col_text)
            row, col = display_to_internal(board, display_row, display_col)
            move = board.location_to_move([row, col])
        except Exception:
            print("输入无法解析，请使用 行,列，例如 3,4。")
            continue
        if move in board.availables:
            return move
        print("该位置不可落子，请重新输入。")


def main():
    parser = argparse.ArgumentParser(description="8x8 AlphaZero-Gomoku terminal demo")
    parser.add_argument("--playouts", type=int, default=200)
    parser.add_argument("--hint-playouts", type=int, default=120)
    parser.add_argument("--ai-first", action="store_true")
    parser.add_argument("--model-file", type=Path, default=REPO_ROOT / "best_policy_8_8_5.model")
    args = parser.parse_args()

    width = height = 8
    n_in_row = 5
    board = Board(width=width, height=height, n_in_row=n_in_row)
    board.init_board(start_player=1 if args.ai_first else 0)
    policy = load_policy(width, height, args.model_file)
    ai = MCTSPlayer(policy.policy_value_fn, c_puct=5, n_playout=args.playouts)

    human_player = board.players[0]
    ai_player = board.players[1]
    if args.ai_first:
        human_player, ai_player = ai_player, human_player
    ai.set_player_ind(ai_player)

    print("8x8 五子棋 AlphaZero 模型已加载：{}".format(args.model_file.name))
    print("AI 每步搜索 {} 次。".format(args.playouts))
    render_board(board, human_player)

    try:
        while True:
            if board.get_current_player() == human_player:
                move = ask_human_move(board, policy, args.hint_playouts)
                board.do_move(move)
            else:
                print("AI 思考中...")
                move = ai.get_action(board)
                print("AI 落子: {},{}".format(*internal_to_display(board, move)))
                board.do_move(move)
            render_board(board, human_player)
            end, winner = board.game_end()
            if end:
                if winner == -1:
                    print("平局。")
                elif winner == human_player:
                    print("你赢了。")
                else:
                    print("AI 获胜。")
                return 0
    except UserQuit:
        print("\n已退出。")
        return 0
    except KeyboardInterrupt:
        print("\n已中断。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
