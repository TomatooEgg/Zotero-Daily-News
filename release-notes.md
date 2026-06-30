## 新功能

- **待推清单**：推送前从标签文献中随机选文，维护待推队列（`zotero_daily_news/queue_manager.py`）
- **预生成**：推送前自动/手动预生成简报与深度解读（`prepare_queue.sh` + launchd 预生成任务）
- **Zotero 回推**：将简报推送到 Zotero 条目子笔记（控制台 → 设置 → Zotero 回推）
- **控制台增强**：队列刷新、预生成、重载定时任务、Zotero 连接测试

## 改进

- PDF 提取与深度解读流程优化
- note-view 交互与样式更新（Markdown 渲染、术语对照）
- launchd 支持推送 + 预生成双定时任务
- 网络环境统一配置（`zotero_daily_news/net_env.py`）

## 配置变更

- 新增 `queue.size`、`queue.prepare_before_minutes`、`queue.pre_generate_deep_read`
- `.env` 可选 `ZOTERO_API_KEY`、`ZOTERO_LIBRARY_ID`
- launchd 标识改为 `com.TomatooEgg.zotero-digest`（含 `.prepare` 子任务）

## 升级提示

1. `git pull` 后运行 `bash install.sh`（如有依赖变更）
2. 在控制台点击「重载定时任务」以安装新的 launchd 配置
3. 若曾安装过旧版定时任务，先清理 LaunchAgents 中所有 `*zotero-digest*` 相关 plist，再在控制台「重载定时任务」
