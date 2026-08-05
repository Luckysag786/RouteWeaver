# 路由织网 RouteWeaver

> VPN 不必“全局接管”：让需要的应用走代理，让国内软件继续直连。

![Version](https://img.shields.io/badge/version-1.3.1-2563eb)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab)
![Windows](https://img.shields.io/badge/Windows-10%2F11-0078d4)
![License](https://img.shields.io/badge/license-MIT-16a34a)
[![CI](https://github.com/Luckysag786/RouteWeaver/actions/workflows/ci.yml/badge.svg)](https://github.com/Luckysag786/RouteWeaver/actions/workflows/ci.yml)

[English](README_EN.md) · [普通用户指南](docs/blog/routeweaver-user-guide.md) · [快速上手](#三分钟上手) · [项目架构](docs/ARCHITECTURE.md) · [能力边界](docs/PLATFORM_LIMITS.md) · [开发故事](docs/blog/routeweaver-launch.md)

## 为什么做这个项目

很多国内用户都有同一种尴尬：打开第三方 VPN/代理的全局模式，国外网站能访问了，但原本很快的国内软件、网盘、视频和办公网站也被绕到远端，速度明显下降；关闭全局模式，又有一部分应用无法正常联网。

路由织网是在现有本地 HTTP/SOCKS5 代理前增加的一层**可审计分流网关**。你只需告诉它“哪些应用或网站需要代理”，它就会根据来源程序和目标域名选择 VPN 出口或物理网络直连。它不修改第三方 VPN 客户端，也不伪造出口 IP。

## 两种分流方式

| 模式 | 适合谁 | 规则命中 | 其他流量 |
|---|---|---|---|
| 正向映射 | 只有少数国外应用需要代理 | 走现有 VPN/代理 | 国内网络直连 |
| 反向隔离 | 大部分流量需要代理，只排除国内应用 | 国内应用/网站直连 | 走现有 VPN/代理 |

## 主要功能

- 按 EXE、运行进程、已安装应用或网站域名配置规则。
- 规则可修改、启停、查重、批量删除，支持双击和快捷键操作。
- 从实时连接活动中一键加入或取消应用/网站规则。
- 支持第三方 HTTP 与 SOCKS5 本地代理作为上游。
- 真实查询直连与代理出口的公网 IP、地区、运营商和数据来源。
- 记录来源进程、目标域名、路由决策和错误，方便判断规则是否生效。
- Windows 系统代理事务式接管；停用或完全退出时恢复原配置。
- 默认开机启动、关闭后驻留托盘，均可在设置中调整。
- 配置导入导出、管理员状态、自助提权和链路诊断。

## 三分钟上手

### 普通用户

1. 在 [Releases](https://github.com/Luckysag786/RouteWeaver/releases) 下载 `RouteWeaver-Windows-Setup-1.3.1.exe`。
2. 保持你原来的 VPN/代理软件处于连接状态，不需要关闭或修改它。
3. 启动路由织网，确认“上游代理”识别为原软件提供的本地 HTTP 或 SOCKS5 地址。
4. 选择“正向映射”或“反向隔离”，添加应用和网站规则。
5. 点击“启用分流”，再用“真实出口测试”和“连接活动”核对结果。
6. 需要停止时使用“停用并恢复”；点右上角 × 默认只是隐藏到托盘。

> 建议先添加一个浏览器或测试网站进行验证，再逐步扩展规则。遇到软件不生效时，先确认它是否使用 Windows 系统代理，以及是否启用了 QUIC/UDP。

### 从源码运行

```powershell
git clone https://github.com/Luckysag786/RouteWeaver.git
cd RouteWeaver
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m routeweaver
```

构建 Windows 单文件程序与安装器：

```powershell
.\scripts\build_windows.ps1
.\scripts\build_installer.ps1
```

Android 构建脚本会在仓库内的忽略目录准备独立工具链：

```powershell
.\scripts\build_android.ps1
```

## Android 版是做什么的

Android 同一用户空间一次只能有一个主要 `VpnService`。当第三方 VPN 已占用该系统槽位时，另一个独立 APK 无权悄悄修改它的分应用名单；强行启动第二条 VPN 反而会断开原连接。

因此 Android 版定位为**规则与验证伴侣**：管理正向/反向规则、识别已安装 VPN、检测兼容性、验证真实出口、导入导出配置，并向实现了 RouteWeaver 交接协议的 VPN 提供商发送规则。若提供商不支持交接，应用会如实提示并复制清单，不会显示虚假的“分流已生效”。详见 [Android 提供商接入协议](docs/ANDROID_PROVIDER_INTEGRATION.md)。

## 能力边界

Windows 稳定后端适用于遵循 Windows 系统代理的应用，以及浏览器 HTTP/HTTPS 流量。以下场景不能仅靠普通 Python 应用完整接管：

- UDP、QUIC、游戏或自建网络协议；
- 明确忽略系统代理的应用；
- 要求在内核层对任意 EXE 强制改写连接的场景。

这类需求需要微软签名的 WFP 驱动或应用自身代理设置。本项目坚持“可验证再宣称”：未经过网关的连接不会显示为已接管。完整说明见 [平台能力边界](docs/PLATFORM_LIMITS.md)。

## 工程结构

```text
RouteWeaver/
├─ .github/            GitHub Actions、Issue 与 PR 模板
├─ android/            Android 规则与验证伴侣
├─ docs/               架构、教程、测试报告与技术博客
├─ installer/          Windows Inno Setup 安装器
├─ scripts/            构建、实网验证与代理事务测试
├─ src/routeweaver/    Windows Python 主程序
├─ tests/              Python 自动化测试
├─ CHANGELOG.md        版本变更记录
├─ CONTRIBUTING.md     贡献指南
├─ LICENSE             MIT 开源许可证
└─ pyproject.toml      Python 工程与依赖配置
```

更完整的模块职责见 [工程目录说明](docs/PROJECT_STRUCTURE.md)。

## 测试与质量

- 27 项 Python 自动化测试。
- Android Java 单元测试与 Debug APK 构建校验。
- 正向/反向、应用/网站、HTTP/SOCKS5 上游的真实连接验证。
- Windows 安装、启动、托盘、开机启动与代理恢复冒烟测试。
- 公网 IP 只展示远端服务实际返回的数据，并保留来源与时间。

完整结果见 [测试报告](docs/TEST_REPORT.md)、[测试指南](docs/TESTING.md) 和 [需求覆盖矩阵](docs/REQUIREMENTS_MATRIX.md)。

## 参与贡献

欢迎提交 Bug、兼容性报告、文档改进和 Pull Request。开始前请阅读 [贡献指南](CONTRIBUTING.md)；安全问题请按 [安全策略](SECURITY.md) 私下报告。

## 许可证与使用提醒

本项目采用 [MIT License](LICENSE)。软件只提供网络路由与诊断能力，请在所在地法律、单位网络规范及相关服务条款允许的范围内使用。项目与任何第三方 VPN/代理品牌均无隶属或背书关系。
