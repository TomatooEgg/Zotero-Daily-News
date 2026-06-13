# Zotero 每日头条弹窗

从 Zotero 文献库中定时抽取待读论文，用 DeepSeek 生成中文阅读简报，并通过 macOS 通知推送。附带本地 Web / 原生窗口控制台，可浏览历史简报、生成深度解读与摘要翻译。

**仓库**：[TomatooEgg/Zotero-Daily-News](https://github.com/TomatooEgg/Zotero-Daily-News)

**平台要求**：macOS 11+，已安装并运行 [Zotero](https://www.zotero.org/)。

## 功能概览

- **定时推送**：按 `config.yaml` 中的时间表，从带指定标签的文献中随机抽取若干篇，生成头条简报并发送系统通知
- **AI 简报**：基于文献元数据（标题、作者、摘要等）生成结构化中文总结，写入 Markdown 并附带 HTML 中转页
- **深度解读**：在笔记视图中基于 PDF 正文调用 DeepSeek 生成更详细的章节解读（可选）
- **摘要翻译**：将英文摘要翻译为中文（可选）
- **专有名词跳转**：总结中的 key terms 可一键在 Zotero PDF 中搜索定位
- **控制台界面**：配置推送参数、手动触发、查看日志、管理历史笔记
- **原生窗口**：双击 `Zotero 简报.app` 打开 pywebview 窗口；支持 `zotero-digest://` 深链接

## 快速开始

### 1. 安装

```bash
git clone https://github.com/TomatooEgg/Zotero-Daily-News.git
cd Zotero-Daily-News
bash install.sh
```

`install.sh` 会：

- 创建 Python 虚拟环境并安装依赖
- 从 `.env.example` 复制 `.env`（若不存在）
- 安装 `terminal-notifier` / `alerter` 到 `bin/`（若系统已安装）
- 注册 launchd 定时任务
- 构建 `Zotero 简报.app` 并在桌面创建快捷方式

### 2. 配置

**环境变量**（`.env`）：

```bash
DEEPSEEK_API_KEY=sk-your-key-here
```

**Zotero**：保持 Zotero 运行，并在 **设置 → 高级** 中开启「Allow other applications on this computer to communicate with Zotero」。

**应用配置**（`config.yaml` 或控制台界面）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `priority_tag` | 优先抽取的标签 | `want` |
| `count` | 每次推送篇数 | `2` |
| `history_days` | 去重天数（近期已推送的不再选） | `14` |
| `schedule` | launchd 定时（可多时段） | 12:01、18:00 |
| `summary_prompt` | 元数据简报 Prompt | 见 `config_manager.py` |
| `pdf_summary` | 深度解读相关配置 | 默认启用 |
| `ui.port` | 本地 Web 服务端口 | `18765` |

### 3. 使用

| 方式 | 命令 / 操作 |
|------|-------------|
| 原生窗口 | 双击 `Zotero 简报.app` 或 `~/Desktop/Zotero 简报.app` |
| 命令行 UI | `bash start_ui.sh` |
| 手动推送 | `bash run.sh` 或 `bash run.sh --force` |
| 仅预览 | `bash run.sh --dry-run` |
| 跳过 AI | `bash run.sh --metadata-only` |
| 测试通知 | `bash run.sh --test-notify` |
| 通知诊断 | `bash run.sh --diagnose-notify` |
| 重建中转页 | `.venv/bin/python rebuild_hubs.py` |

点击 macOS 通知后会打开 HTML 中转页，可查看完整简报、跳转 Zotero 条目或 PDF。

## 项目结构

```
Zotero-Daily-News/
├── digest.py           # 主流程：抽文献 → AI 总结 → 写文件 → 通知
├── app.py              # Flask 控制台与笔记 API
├── launcher.py         # 启动 Web 服务 + pywebview 窗口
├── config.yaml         # 用户配置
├── config_manager.py   # 配置读写
├── summary_io.py       # Markdown / HTML 输出
├── notes_index.py      # 历史笔记索引
├── note_view.py        # 笔记阅读视图渲染
├── deep_read.py        # PDF 深度解读
├── abstract_zh.py      # 摘要中译
├── pdf_text.py         # PDF 文本提取
├── zotero_links.py     # Zotero 链接与 PDF 检索
├── notifier.py         # macOS 通知
├── url_handler.py      # 深链接 zotero-digest://
├── launchd_mgr.py      # launchd 定时任务
├── rebuild_hubs.py     # 批量重建 HTML 中转页
├── install.sh          # 一键安装
├── build_app.sh        # 构建 .app
├── run.sh              # 运行 digest.py
├── start_ui.sh         # 运行 launcher.py
├── templates/          # Jinja2 模板
├── static/             # 笔记视图 CSS / JS
├── summaries/          # 生成的 Markdown（运行时，已 gitignore）
├── hubs/               # HTML 中转页（运行时，已 gitignore）
├── logs/               # launchd 日志（运行时，已 gitignore）
├── bin/                # terminal-notifier、alerter（安装时复制）
└── Zotero 简报.app/    # 可双击启动（构建产物，已 gitignore）
```

## 依赖

见 `requirements.txt`，主要包括：

- `pyzotero` — Zotero 本地 API
- `openai` — DeepSeek API（OpenAI 兼容）
- `flask` — Web 控制台
- `pywebview` — 原生窗口（可选，缺失时回退到浏览器）
- `pypdf` — PDF 文本提取
- `pyyaml`、`markdown`

系统工具（建议通过 Homebrew 安装）：

```bash
brew install terminal-notifier
brew install vjeantet/tap/alerter   # 可选，通知「查看总结」按钮
```

## 常见问题

**无法连接 Zotero**  
确认 Zotero 已启动，且高级设置中允许本地 API 通信。

**通知不显示**  
运行 `bash run.sh --diagnose-notify` 检查；确认系统通知权限已授予 Terminal / Python / 简报 App。

**DeepSeek 调用失败**  
检查 `.env` 中 `DEEPSEEK_API_KEY`；无 Key 时可用 `--metadata-only` 仅输出元数据摘要。

**修改定时后未生效**  
在控制台点击「重载定时任务」，或运行：

```bash
.venv/bin/python -c "from launchd_mgr import write_plist, reload_launchd; from config_manager import load_config; c=load_config(); write_plist(c); reload_launchd(c)"
```


## 许可证

[MIT License](LICENSE)
