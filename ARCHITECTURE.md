# 自动化客户端结构

## 正式入口

`main.py` 启动桌面客户端。客户端负责选择游戏窗口、选择任务、启动和停止，不直接编写游戏流程。

## 分层

- `client/`: Tkinter 桌面界面，只处理用户操作和状态展示。
- `application/`: 应用服务层。`AutomationController` 负责把界面请求连接到游戏 Agent 和任务插件。
- `domain/`: 与界面无关的任务模型、状态和运行上下文。
- `tasks/`: 日常任务插件。`TaskRegistry` 注册任务，`tasks/base.py` 定义生命周期；每个具体任务应独立成文件或包。
- `agent/`、`core/`、`vision/`: 游戏窗口发现、截图、输入、视觉识别和状态机等基础能力。
- `templates/`: 游戏界面模板资源。
- `run_*.py`、`diagnose_*.py`、`test_*.py`: 历史实验和诊断脚本，不是客户端运行入口。

## 新增任务约定

1. 在 `tasks/` 新建任务类，继承 `AutomationTask`。
2. 在 `run()` 中创建或驱动该任务自己的状态机；通过 `TaskContext.agent` 使用截图、识别和点击能力。
3. 在循环中检查 `self._stop_event`，确保客户端的停止按钮可以及时生效。
4. 用 `TaskSnapshot` 汇报阶段、进度和错误。
5. 在 `TaskRegistry.register_builtins()` 中注册任务。

当前四个内置任务已经注册，但仍是安全占位实现，在收到准确流程前不会点击游戏。
