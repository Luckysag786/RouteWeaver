---
layout: default
title: 路由织网 RouteWeaver
---

# 别再让全局 VPN 拖慢所有软件

路由织网 RouteWeaver 是一款面向中国用户使用习惯设计的开源分流工具：在保留现有 VPN/代理的同时，让真正需要代理的应用和网站走代理，其余国内软件继续使用本地直连。

[阅读完整开发故事](blog/routeweaver-launch.md) · [查看 GitHub 项目](https://github.com/Luckysag786/RouteWeaver) · [查看全部版本](https://github.com/Luckysag786/RouteWeaver/releases)

## 直接下载

### Windows 用户（推荐）

[下载 Windows 1.3.1 安装版](https://github.com/Luckysag786/RouteWeaver/releases/download/v1.3.1/RouteWeaver-Windows-Setup-1.3.1.exe)

安装版包含开始菜单入口、开机启动选项和卸载程序，适合普通用户。

[下载 Windows 1.3.1 免安装版](https://github.com/Luckysag786/RouteWeaver/releases/download/v1.3.1/RouteWeaver-Windows-1.3.1.exe)

免安装版适合临时测试；配置仍保存在当前 Windows 用户的数据目录中。

### Android 测试版

[下载 Android 1.2.0 Debug APK](https://github.com/Luckysag786/RouteWeaver/releases/download/v1.3.1/RouteWeaver-Android-1.2.0-debug.apk)

Android 包目前使用 Debug 侧载签名，定位为规则管理、出口验证和兼容提供商交接伴侣，不会接管另一个应用已经建立的 VPN。

### 文件校验

[下载 SHA256SUMS.txt](https://github.com/Luckysag786/RouteWeaver/releases/download/v1.3.1/SHA256SUMS.txt)

```text
Windows 安装版  9D1A74AD135B23A5749D526E3DB276E33D1366A80D402174A092F5F54469B7E2
Windows 免安装版 894A88533BBB96892F66308F7EA0159F31ABDC644F9F19822A31909EF0C63329
Android Debug   B630A0B20FB08E8603235EC2CF4F9B7768F23A8A8BD6FD3AE7BA394F091D1E85
```

> 下载由 GitHub Releases 提供。如果当前网络访问 GitHub 较慢，请稍后重试；不要从来源不明的网盘或二次打包站下载。

## 一句话说明

- 少数国外应用需要代理：使用**正向映射**。
- 大多数流量走代理，只排除国内应用：使用**反向隔离**。
- 不确定有没有生效：查看**真实出口 IP**和**连接活动**。

项目坚持公开能力边界：Windows 当前覆盖遵循系统代理的 TCP/HTTP(S) 流量；Android 版是规则与验证伴侣，不会冒充可以接管另一个 VPN 的系统流量。
