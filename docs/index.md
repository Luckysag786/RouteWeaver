---
layout: default
title: 路由织网 RouteWeaver
---

# 别再让全局 VPN 拖慢所有软件

路由织网 RouteWeaver 是一款面向中国用户使用习惯设计的开源分流工具：在保留现有 VPN/代理的同时，让真正需要代理的应用和网站走代理，其余国内软件继续使用本地直连。

[普通用户使用指南](blog/routeweaver-user-guide.md) · [阅读开发故事](blog/routeweaver-launch.md) · [查看 GitHub 项目](https://github.com/Luckysag786/RouteWeaver) · [查看全部版本](https://github.com/Luckysag786/RouteWeaver/releases)

## 最新更新：1.3.2（2026-08-08）

- 修复部分网络环境中 `ipwho.is`、`ifconfig.co` TLS 提前断流后，VPN 上游出口无法显示公网 IP 的问题；现在使用多服务并发容错，健康服务会优先返回。
- 修正 HTTP CONNECT 建链时序和 TCP 半关闭处理，降低 HTTPS 连接偶发断开、响应被提前截断的问题。
- 加强 Windows 系统代理、事务备份、PAC、WinHTTP、HTTP/SOCKS5 和常见本地代理端口自动识别，并保存识别来源和更新时间。
- 新增 Windows 单实例安全锁：软件只保留一个进程，重复启动会提示打开已有窗口，不会重复建立网关或托盘进程。
- 34 项 Python 自动化测试通过，并完成真实直连/VPN 双出口、免安装程序和安装包构建验证。

[查看 1.3.2 完整更新说明](RELEASE_NOTES_1.3.2.md)

## 直接下载

### Windows 用户（推荐）

[下载 Windows 1.3.2 安装版](https://github.com/Luckysag786/RouteWeaver/releases/download/v1.3.2/RouteWeaver-Windows-Setup-1.3.2.exe)

安装版包含开始菜单入口、开机启动选项和卸载程序，适合普通用户。

[下载 Windows 1.3.2 免安装版](https://github.com/Luckysag786/RouteWeaver/releases/download/v1.3.2/RouteWeaver-Windows-1.3.2.exe)

免安装版适合临时测试；配置仍保存在当前 Windows 用户的数据目录中。

### Android 测试版

[下载 Android 1.2.0 Debug APK](https://github.com/Luckysag786/RouteWeaver/releases/download/v1.3.2/RouteWeaver-Android-1.2.0-debug.apk)

Android 包目前使用 Debug 侧载签名，定位为规则管理、出口验证和兼容提供商交接伴侣，不会接管另一个应用已经建立的 VPN。

### 文件校验

[下载 SHA256SUMS.txt](https://github.com/Luckysag786/RouteWeaver/releases/download/v1.3.2/SHA256SUMS.txt)

```text
Windows 安装版  7A0D9F34F99D25EAF763CCA7B72091FC6846E998CE2C2478158A1AB8D2C375EF
Windows 免安装版 00AC7556C68070272B482EDCFC2826370F513DA3625BAC17F9871A68C0539B87
Android Debug   B630A0B20FB08E8603235EC2CF4F9B7768F23A8A8BD6FD3AE7BA394F091D1E85
```

> 下载由 GitHub Releases 提供。如果当前网络访问 GitHub 较慢，请稍后重试；不要从来源不明的网盘或二次打包站下载。

## 一句话说明

- 少数国外应用需要代理：使用**正向映射**。
- 大多数流量走代理，只排除国内应用：使用**反向隔离**。
- 不确定有没有生效：查看**真实出口 IP**和**连接活动**。

项目坚持公开能力边界：Windows 当前覆盖遵循系统代理的 TCP/HTTP(S) 流量；Android 版是规则与验证伴侣，不会冒充可以接管另一个 VPN 的系统流量。
