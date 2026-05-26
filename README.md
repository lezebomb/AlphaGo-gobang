# AlphaGo-gobang

这是人工智能科学与技术课程小组作业的项目仓库，主题为 **AlphaGo 与围棋 AI 家族**。仓库包含一份实验报告生成脚本、最终版报告，以及一个便于课堂演示的 10x10 五子棋 AlphaZero 风格复现实验。

## 项目内容

- `AlphaZero_Gomoku/`：基于 AlphaZero 思路改造的五子棋实验代码，包含棋盘环境、MCTS、自我对弈、轻量策略-价值模型和终端对弈脚本。
- `AlphaZero_Gomoku/models/lightweight_policy_10x10.json`：已经训练好的 10x10 轻量模型，可直接用于演示。
- `AlphaZero_Gomoku/play_gomoku_10x10.py`：人机对弈入口，棋盘坐标为行号自上而下 1-10、列号自左向右 1-10。
- `AlphaZero_Gomoku/train_lightweight_10x10.py`：轻量模型自我对弈训练脚本。
- `AlphaZero_Gomoku/experiments/evaluate_10x10_model.py`：模型评估脚本，支持随机基线、战术基线和 MCTS 搜索次数扫描。
- `reports/build_alphago_report_10x10.py`：实验报告生成脚本。
- `AlphaGo与围棋AI家族_实验报告_最终充实版.docx`：已排版的最终实验报告。

## 快速运行

进入项目目录后安装依赖：

```bash
pip install numpy python-docx matplotlib
```

与 10x10 强化版五子棋 AI 对弈：

```bash
cd AlphaZero_Gomoku
python play_gomoku_10x10.py --playouts 120
```

常用交互方式：

- 输入 `行,列` 落子，例如 `5,5`
- 输入 `hint` 获取模型建议
- 输入 `q` 退出

重新训练轻量模型：

```bash
cd AlphaZero_Gomoku
python train_lightweight_10x10.py --games 28 --playouts 24
```

运行模型评估：

```bash
cd AlphaZero_Gomoku
python experiments/evaluate_10x10_model.py --games 10 --playouts 80 --sweep 30,60,100
```

重新生成实验报告：

```bash
python reports/build_alphago_report_10x10.py
```

## 技术路线

本项目用 10x10 五子棋替代完整围棋进行课堂复现，保留 AlphaGo/AlphaZero 系列中的核心思想：

1. 用棋盘状态作为马尔可夫决策过程中的状态。
2. 用策略函数给出候选落子的先验概率。
3. 用价值函数估计当前局面对当前玩家的胜负倾向。
4. 用 MCTS 在策略先验和价值评估的引导下进行局部搜索。
5. 通过自我对弈产生训练样本，使搜索结果反过来改进策略-价值模型。

为了降低运行门槛，仓库中的 10x10 演示模型没有依赖 PyTorch/TensorFlow，而是使用基于棋形特征的轻量策略-价值模型，仍然兼容 `mcts_alphaZero.py` 的 `policy_value_fn(board)` 接口，适合课堂展示和报告复现。

## 来源说明

`AlphaZero_Gomoku/` 的基础框架参考了开源项目 `junxiaosong/AlphaZero_Gomoku`，本仓库在此基础上增加了 10x10 轻量训练、坐标显示修正、模型评估脚本和课程报告生成流程。原始项目许可证见 `AlphaZero_Gomoku/LICENSE`。
