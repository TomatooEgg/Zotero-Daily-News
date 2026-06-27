# Zotero 每日头条弹窗

把 Zotero 里标记为 `want` 的论文自动整理成每日简报：定时筛选、调用 DeepSeek 生成中文摘要和深度解读、弹出系统通知，并可把生成的 News 回写到 Zotero 笔记。

## 快速开始（先看这里）

推荐普通用户优先使用发行包，不需要手动编辑 `.env`，也不需要自己注册系统定时任务。

1. 安装并启动 Zotero Desktop。
2. 在 Zotero 中启用本机 API：`Settings -> Advanced -> Allow other applications on this computer to communicate with Zotero`。
3. 给想看的论文打上 `want` 标签。这个标签可以在设置里改。
4. 从 [Releases](https://github.com/TomatooEgg/Zotero-Daily-News/releases) 下载适合系统的安装包。
5. 启动应用，按照首次启动向导填写 DeepSeek 和 Zotero 配置。
6. 在控制面板点击 **Test Notification** 或 **Run Now**，确认能生成并打开 News。

完成后，应用会按设置的时间自动准备队列和推送通知。生成的 News 会显示在控制面板的 **Notes** 页。

## 安装方式

### Windows：MSI 安装包

适合大多数 Windows 10/11 x86_64 用户。

1. 下载 `Zotero-Daily-News-Windows-x86_64.msi`。
2. 双击安装。
3. 从桌面快捷方式或开始菜单启动 **Zotero Daily News**。
4. 首次启动时完成配置向导。

Windows 版默认使用图形界面和系统托盘。关闭主窗口后可以继续留在后台，托盘菜单可以重新打开窗口或退出应用。

### Windows：Portable ZIP

适合不想安装、临时试用或需要放在可移动目录中的用户。

1. 下载 `Zotero-Daily-News-Windows-x86_64-Portable.zip`。
2. 解压到一个可写目录，例如 `D:\Apps\Zotero Daily News`。
3. 运行解压目录里的 `Zotero Daily News.exe`。
4. 首次启动时完成配置向导。

Portable 版本不会把运行时文件写进解压目录。配置、日志、队列和生成的 News 仍保存在用户目录中。

### macOS：DMG

适合 Apple Silicon Mac 用户。

1. 下载 `Zotero-Daily-News-macOS-arm64.dmg`。
2. 打开 DMG。
3. 把 `Zotero 简报.app` 拖到“应用程序”。
4. 从“应用程序”启动，并完成配置向导。

如果首次启动被系统拦截，可以右键打开，或在系统设置的安全性页面允许打开。Intel Mac 用户可以源码运行，或在 Intel Mac 上执行 `bash build_dmg.sh` 自行构建。

### 源码运行

适合熟悉命令行、需要参与开发或需要自行构建发行包的用户。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m zotero_daily_news.launcher
```

macOS/Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m zotero_daily_news.launcher
```

源码运行时也可以使用仓库根目录的包装脚本：

| 操作 | Windows | macOS/Linux |
| --- | --- | --- |
| 启动控制面板 | `.\start_ui.ps1` | `bash start_ui.sh` |
| 手动推送 | `.\run.ps1 --push-queue` | `bash run.sh --push-queue` |
| 刷新队列 | `.\run.ps1 --refresh-queue` | `bash run.sh --refresh-queue` |
| 预生成队列 | `.\prepare_queue.ps1` | `bash prepare_queue.sh` |
| 仅预览不写入 | `.\run.ps1 --dry-run --push-queue` | `bash run.sh --dry-run --push-queue` |
| 跳过 AI，只看元数据 | `.\run.ps1 --metadata-only` | `bash run.sh --metadata-only` |

macOS 源码用户也可以执行：

```bash
bash install.sh
```

`install.sh` 会创建 Python 环境、安装依赖、构建 macOS app bundle 并创建桌面快捷方式。它不会在安装时直接启用定时任务；先启动应用并完成首启向导，再在控制面板里启用定时推送。

## 首次启动配置

首次启动会打开配置向导。按向导填写并验证通过后，应用才会启用 Windows Task Scheduler 或 macOS launchd 定时任务。

| 字段 | 是否必填 | 获取方式 |
| --- | --- | --- |
| DeepSeek API Key | 必填 | 登录 [DeepSeek Platform API Keys](https://platform.deepseek.com/api_keys)，创建新 Key 后粘贴到向导。若验证提示余额或额度不足，需要先在 DeepSeek 账户中处理余额或额度。 |
| DeepSeek Base URL | 通常不用改 | 默认是 `https://api.deepseek.com`。只有使用兼容代理或网关时才修改。 |
| DeepSeek briefing model | 通常不用改 | 用于每日简报。只有账号或网关要求不同模型名时才修改。 |
| DeepSeek deep-read model | 通常不用改 | 用于 PDF 深度解读。可以和 briefing model 分开配置。 |
| Zotero API Key | 必填 | 登录 Zotero，打开 [API Keys](https://www.zotero.org/settings/keys) 或 [Security](https://www.zotero.org/settings/security)，创建 private key，允许 personal library access，并启用 write access。 |
| Zotero Library ID | 个人库通常留空 | 留空时应用会通过 Zotero API Key 自动识别数字 user ID。自动识别失败时，在 Zotero API Keys 页面复制数字 user ID。 |
| Zotero Local API | 必须开启 | 不需要 Key。在 Zotero Desktop 中启用本机 API，并保持 Zotero 运行。 |

可以手动检查 Zotero Local API：

Windows PowerShell：

```powershell
Invoke-RestMethod "http://127.0.0.1:23119/api/users/0/items/top?limit=1"
```

macOS/Linux：

```bash
curl "http://127.0.0.1:23119/api/users/0/items/top?limit=1"
```

## 如何使用

1. 在 Zotero 里给论文打上 `want` 标签。
2. 打开控制面板，在 **Settings** 页确认推送时间、队列大小、模型名和输出目录。
3. 点击 **Refresh Queue** 生成待推清单。
4. 点击 **Run Now** 手动生成一次 News 并发送通知。
5. 到 **Notes** 页查看已生成和待回写的 News。
6. 在 News 详情里点击 **Backfill Zotero**，可以把生成内容写回 Zotero 笔记。
7. 需要后台运行时，把窗口最小化或关闭到系统托盘。

常用页面：

| 页面 | 用途 |
| --- | --- |
| **Notes** | 查看已生成 News、打开详情、定位本地文件、回写 Zotero |
| **Push & Logs** | 刷新队列、预生成队列、手动推送、查看运行日志 |
| **Settings** | 配置 DeepSeek、Zotero、推送时间、标签、队列和输出目录 |

生成的 News 默认保存在用户运行时目录，而不是仓库目录或安装目录。具体路径见“配置与默认值”。

## 为什么需要它

Zotero 适合收藏论文，但每天回到 Zotero 里逐条检查、阅读摘要、决定先读哪篇，仍然很耗时间。本项目把这个流程压缩为一个本地小工具：

- 在 Zotero 中用一个标签维护“待读论文”。
- 到点自动生成待推清单和中文简报。
- 通过 macOS/Windows 系统通知提醒你。
- 在本地控制面板里查看 News、日志、队列和定时任务。
- 需要时把生成内容回写到 Zotero 对应条目的笔记中。

## 它会做什么

### 弹窗

到点弹出一条系统通知，提示今天值得看的论文。

Windows 版通知带有 **Open News** 按钮，点击即可打开生成的 News。

![弹窗](https://github.com/user-attachments/assets/1d87d011-8d66-4674-b3fd-53b023e442c4)

### 基础简报

对标题、摘要、期刊、作者和关键词做结构化总结，生成可读的中文简报。

![基础简报](https://github.com/user-attachments/assets/91243bc2-dd0d-4f5f-b848-c5f1c1b18c84)

### 链接 Zotero

生成的 News 会保留 Zotero 条目链接，方便回到原始条目。需要时可以在 News 详情里点击 **Backfill Zotero**，把内容写回 Zotero 笔记。

![链接 Zotero](https://github.com/user-attachments/assets/7cb22dd1-7f02-49df-914a-074837cca5a9)

### 历史记录

记录已推送、已生成、待处理的条目，避免重复推送。

![历史记录](https://github.com/user-attachments/assets/f59b74b6-dbc6-4c14-9fbb-ed91ddf83859)

### 摘要翻译

默认输出中文，可把英文摘要整理成更适合快速阅读的中文说明。

![摘要翻译](https://github.com/user-attachments/assets/0ae97039-1637-4f83-a92b-67d3ab091e37)

### 深度解读

可读取 PDF 正文并生成更长的结构化解读，适合先判断一篇论文是否值得精读。

![深度解读](https://github.com/user-attachments/assets/b3e8ab46-d3a3-4087-931d-315171452c7e)

### 自定义优先 tag 与发送时间

默认读取 `want` 标签。默认推送时间是 `10:00` 和 `18:00`，也可以在控制面板中调整。

![自定义优先 tag 与发送时间](https://github.com/user-attachments/assets/76b99412-2f3f-4faa-a1ee-8921f7f16696)

### 自定义总结 prompt

可以调整摘要 prompt、PDF 深度解读 prompt、模型名、队列大小和预生成时间。

![自定义总结 prompt](https://github.com/user-attachments/assets/d51ba67a-6e2f-41ef-bc13-44db8fbb9760)

## 配置与默认值

内置默认值的唯一来源是 `config_manager.DEFAULT_CONFIG`。

`config.example.yaml` 只是给源码用户看的示例配置。运行时配置会写入用户配置目录，不会再写入仓库根目录。

| Key | 默认值 |
| --- | --- |
| `priority_tag` | `want` |
| `count` | `2` |
| `history_days` | `14` |
| `queue.size` | `4` |
| `queue.prepare_before_minutes` | `120` |
| `schedule` | `10:00`, `18:00` |
| `ui.port` | `18765` |

用户配置路径：

| 平台 | 配置和 `.env` |
| --- | --- |
| Windows | `%APPDATA%\Zotero Daily News\` |
| macOS | `~/Library/Application Support/Zotero Daily News/` |
| Linux | `$XDG_CONFIG_HOME/zotero-daily-news/` 或 `~/.config/zotero-daily-news/` |

运行时状态路径：

| 平台 | 运行时文件 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Zotero Daily News\` |
| macOS | `~/Library/Application Support/Zotero Daily News/` |
| Linux | `$XDG_STATE_HOME/zotero-daily-news/` 或 `~/.local/state/zotero-daily-news/` |

运行时文件包括 `history.json`、`queue.json`、`pending_publish.json`、`summaries/`、`hubs/` 和 `logs/`。

## 构建发行包

### Windows

在 Windows 上执行：

```powershell
.\build_windows.ps1
```

输出：

- `dist\Zotero-Daily-News-Windows-x86_64.msi`
- `dist\Zotero-Daily-News-Windows-x86_64-Portable.zip`

### macOS

在 macOS 上执行：

```bash
bash build_dmg.sh
```

输出：

- `dist/Zotero-Daily-News-macOS-<arch>.dmg`

## CI 与测试

GitHub Actions 会在 Windows 和 macOS 上运行测试。

手动触发 workflow 或推送 tag 时，会额外构建：

- Windows MSI
- Windows Portable ZIP
- macOS DMG

macOS DMG 构建完成后会自动校验文件可挂载。

## 安全

LLM/Markdown 输出在渲染为 HTML 前会经过清洗。会移除不安全标签、事件属性、`javascript:` URL 和图片，同时保留 Markdown 表格、代码块、Mermaid class、Zotero 链接等必要内容。

## 项目结构

```text
Zotero-Daily-News/
├── zotero_daily.py          # 打包统一入口
├── zotero_daily_news/       # 应用包
│   ├── launcher.py          # 本地控制面板入口
│   ├── digest.py            # 队列、摘要生成、推送主流程
│   ├── notifier.py          # macOS/Windows 系统通知
│   ├── scheduler.py         # launchd / Task Scheduler 管理
│   ├── config_manager.py    # 默认配置、配置加载与迁移
│   ├── env_store.py         # 用户配置目录中的 .env 管理
│   ├── md_render.py         # Markdown 渲染与 HTML 清洗
│   └── notes_index.py       # 已生成 News 索引
├── templates/               # 控制面板和 News 视图模板
├── static/                  # 前端静态资源
├── prompts/                 # 默认 prompt
├── tests/                   # 单元测试
├── build_windows.ps1        # Windows MSI/Portable 构建
├── build_dmg.sh             # macOS DMG 构建
└── .github/workflows/ci.yml # 测试与发行包构建
```

## 依赖

- Python 3.12
- Zotero Desktop，本机 API 需要开启
- DeepSeek API Key
- Zotero API Key，用于回写 Zotero 笔记
- Windows 10/11 x86_64，或 macOS 11+

主要 Python 依赖见 `requirements.txt`。

## 常见问题

**连接不上 Zotero**

确认 Zotero Desktop 已启动，并开启本机 API：

`Settings -> Advanced -> Allow other applications on this computer to communicate with Zotero`

**DeepSeek 验证失败**

检查 API Key、Base URL、模型名和账户余额。使用代理或兼容网关时，Base URL 和模型名要与网关保持一致。

**Zotero 回写失败**

重新创建 Zotero API Key，确保允许 personal library access，并启用 write access。

**Windows 通知怎么打开 News**

点击通知里的 **Open News** 按钮，或在控制面板的 **Notes** 页打开对应 News。

**看不到生成的 News**

打开控制面板的 **Notes** 页。Windows 默认文件目录是 `%LOCALAPPDATA%\Zotero Daily News\summaries` 和 `%LOCALAPPDATA%\Zotero Daily News\hubs`，设置页会显示实际解析后的路径。

**修改定时任务后没有生效**

在控制面板保存设置后，使用定时任务重载按钮。Windows 使用 Task Scheduler，macOS 使用 launchd。

## 许可证

[MIT License](LICENSE)
