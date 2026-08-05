# 贡献指南

感谢你愿意帮助改进路由织网。中文或英文 Issue 都可以；描述越具体，问题越容易复现。

## 提交问题前

1. 阅读 [平台能力边界](docs/PLATFORM_LIMITS.md)，确认问题属于当前后端可覆盖的流量。
2. 搜索已有 Issue，避免重复提交。
3. 隐去公网 IP、用户名、安装路径、代理凭据和公司内部域名等隐私信息。

## 本地开发

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

代码主要位于 `src/routeweaver/`，测试位于 `tests/`。Android 工程位于 `android/`。

## Pull Request 约定

- 每个 PR 聚焦一个明确问题，说明动机、实现和验证方式。
- 功能变更应补充测试；用户可见变化应更新 README 或 CHANGELOG。
- 不要提交构建产物、SDK、真实代理配置、日志或个人路径。
- 不得通过结束、重启或改写第三方 VPN 客户端来实现测试。
- UI 文案以中文为主；新增核心说明时尽量同步英文摘要。

提交即表示你同意按本项目 MIT License 提供贡献。
