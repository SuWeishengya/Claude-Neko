# Contributing to Claude Neko

感谢你的贡献！无论是 Bug 报告、功能建议、代码贡献还是文档改进，都很欢迎。

## 快速开始

```bash
# 环境搭建（需要 --system-site-packages 访问系统 GTK3）
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
pip install ruff  # 代码规范

# 运行测试
bash test_all.sh

# 检查代码规范
ruff check
```

## 提交流程

1. **Fork** 仓库
2. 创建分支：`git checkout -b feature/your-feature`
3. 编写代码，确保通过测试和 ruff 检查
4. 提交：`git commit -m "feat: 描述"`
5. Push 并创建 Pull Request

## Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

- `feat:` — 新功能
- `fix:` — Bug 修复
- `docs:` — 文档
- `chore:` — 工具、配置
- `refactor:` — 重构

## 代码规范

- Python 3.8+ 兼容
- 通过 `ruff check`（无错误）
- 通过 `bash test_all.sh`（38 tests）
- 遵循现有代码风格

## 项目结构

```
assets/cat/         精灵图素材，按状态分目录
server.py           HTTP 后端，状态机核心
neko_widget.py      GTK3 悬浮窗，渲染 + 交互
hook_bridge.py      Claude Code Hook 事件桥接
updater.py          在线更新模块
claude_monitor.py    手动模式轮询
neko                CLI 管理工具
install.sh          一键安装脚本
test_all.sh         38 项测试
```

## 添加新状态动画

1. 在 `assets/cat/` 下创建新状态目录，放入 PNG 帧（frame_0.png, frame_1.png, ...）
2. 在 `server.py` `state` 的状态机处理中添加新 mode
3. 在 `neko_widget.py` `COLORS` 和 `MSGS` 中添加对应配置
4. 精灵图会自动加载，无需修改 `load_sprites()`

## 发布流程

1. 更新 `version.json` 版本号
2. 更新 `CHANGELOG.md`
3. 创建 Git tag：`git tag vX.Y.Z && git push --tags`
4. GitHub Release 自动创建

## 问题反馈

- Bug → [GitHub Issues](https://github.com/SuWeishengya/Claude-Neko/issues/new?template=bug_report.md)
- 功能建议 → [Feature Request](https://github.com/SuWeishengya/Claude-Neko/issues/new?template=feature_request.md)
