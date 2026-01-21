# CyberBoss - 赛博司马特 AI 老板

一个监督自媒体内容创作的 AI Agent。

## 快速开始

```bash
# 激活虚拟环境
.venv\Scripts\Activate.ps1

# 运行
python main.py
```

## 项目结构

```
├── main.py          # 程序入口
├── config/          # 配置管理
├── core/            # 核心逻辑
├── prompts/         # 提示词
├── context/         # 上下文加载
├── ui/              # 用户界面
└── data/            # 数据文件
```

## Electron 桌面版（方案B）

开发模式（需要本机有 Python）：
```bash
cd electron
npm install
npm run dev
```

打包后端（每个系统分别打包）：
```bash
pip install pyinstaller
./scripts/build_backend.ps1   # Windows
./scripts/build_backend.sh    # macOS/Linux
```

将生成的 `dist/backend(.exe)` 复制到 `electron/backend/`，然后打包 Electron：
```bash
cd electron
npm run dist
```
