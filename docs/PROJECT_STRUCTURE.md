# 工程目录说明

项目采用“平台代码分离、共用策略概念、构建产物不入库”的组织方式。

| 路径 | 职责 | 是否进入发布源码 |
|---|---|---|
| `.github/` | CI、依赖更新、Issue/PR 模板 | 是 |
| `src/routeweaver/` | Windows UI、规则引擎、网关、系统集成 | 是 |
| `tests/` | Python 单元测试与本地网关测试 | 是 |
| `android/` | Android 规则管理与提供商交接伴侣 | 是 |
| `installer/` | Inno Setup 安装器定义 | 是 |
| `scripts/` | Windows/Android 构建和真实链路测试 | 是 |
| `docs/` | 用户文档、架构、边界、博客和测试报告 | 是 |
| `artifacts/` | EXE、安装器、APK、测试 JSON | 否；通过 Release 发布 |
| `.toolchains/` | 本地 Android SDK/JDK/Gradle | 否 |
| `build/`、`dist/` | PyInstaller 临时输出 | 否 |
| `.install-smoke/` | 本地安装冒烟数据 | 否 |

## Windows 模块

- `app.py`：Tk UI 与用户交互编排。
- `gateway.py`：HTTP/HTTPS CONNECT 分流网关。
- `policy.py`：正向/反向规则决策。
- `upstream.py`：HTTP/SOCKS5 上游连接。
- `windows_proxy.py`：系统代理事务和异常恢复。
- `windows_single_instance.py`：Windows 命名互斥体与重复启动保护。
- `windows_process.py`：本地连接来源进程识别。
- `windows_catalog.py`：运行进程和已安装应用目录。
- `ip_geo.py`、`rule_probe.py`：多服务公网出口与规则级验证。
- `config.py`、`models.py`：配置持久化与数据模型。

## 发布原则

源码仓库不包含本机 SDK、用户配置、日志、第三方 VPN 信息或二进制构建缓存。可安装文件使用语义化版本 Git Tag 和 GitHub Release 分发，并附 SHA-256 校验值。
