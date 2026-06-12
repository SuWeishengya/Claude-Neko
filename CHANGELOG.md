# Changelog

All notable changes to Claude Neko will be documented in this file.

## [0.1.0] - 2026-06-12

### Added

- **10 种状态动画** — idle/think/busy/typing/subagent/attention/heart/happy/error/sleep，各有独立精灵图
- **状态粒子特效** — sleep 飘 z、busy 旋转点、typing 代码符号、heart 爱心
- **6 种颜色方案** — 橘/蓝/粉/灰/黑/白，多实例自动分配，右键实时切换
- **审批提示框** — 叠加在猫胸口，Cairo 半透明绘制
- **右键菜单** — Cairo 自绘透明窗口，检查更新/帮助/颜色切换/反馈问题/停止
- **左键统计弹窗** — 显示 Token 用量、会话数、运行中工具数
- **在线更新** — `neko update` CLI 命令 + updater.py，GitHub Release 检测 + 下载 + 备份 + 安装
- **版本管理** — version.json + `neko version`
- **CLI 工具** — `neko start/stop/restart/enable/disable/status/version/update`
- **手动模式** — `neko start` 启动独立小猫，监听所有 Claude 会话
- **拖拽移动** — motion 检测区分点击/拖拽
- **Hook 桥接日志** — hook_bridge.log 用于问题排查

### Changed

- 审批框从猫头顶移到胸口叠加显示，PAD_TOP 70→5px，窗口高度 220→155px
- typing 动画从 4 帧简化为 2 帧
- 轮询间隔 500ms→200ms
- 状态机增加 prompt_active/pending_heart 标记

### Fixed

- 手动模式 session 存活检查导致自动关闭（manual- 前缀豁免）
- Cairo 不支持 emoji（✨→★, ⏳→>>）
- 审批框在终端操作完成后不消失
- 工具间 think 状态闪回 busy
- 多实例颜色方案实时切换
- post_tool_use 后 stuck in busy 问题

### Infrastructure

- install.sh 使用 rsync --delete 同步 assets
- test_all.sh 38 项测试
- 清理 settings.json 旧 claude-desktop-pet 配置
- ruff 代码规范检查（ruff.toml）
- .github/ISSUE_TEMPLATE（Bug Report + Feature Request）
- .github/PULL_REQUEST_TEMPLATE.md
- CONTRIBUTING.md 贡献指南
- packaging/aur/（PKGBUILD + .install，Arch Linux AUR 包）
- docs/ARCHITECTURE.md 架构文档
- docs/ROADMAP.md 开发路线图
