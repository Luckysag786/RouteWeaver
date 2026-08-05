---
layout: default
title: 路由织网 RouteWeaver
---

# 别再让全局 VPN 拖慢所有软件

路由织网 RouteWeaver 是一款面向中国用户使用习惯设计的开源分流工具：在保留现有 VPN/代理的同时，让真正需要代理的应用和网站走代理，其余国内软件继续使用本地直连。

[阅读完整开发故事](blog/routeweaver-launch.md) · [查看 GitHub 项目](https://github.com/Luckysag786/RouteWeaver) · [下载安装](https://github.com/Luckysag786/RouteWeaver/releases)

## 一句话说明

- 少数国外应用需要代理：使用**正向映射**。
- 大多数流量走代理，只排除国内应用：使用**反向隔离**。
- 不确定有没有生效：查看**真实出口 IP**和**连接活动**。

项目坚持公开能力边界：Windows 当前覆盖遵循系统代理的 TCP/HTTP(S) 流量；Android 版是规则与验证伴侣，不会冒充可以接管另一个 VPN 的系统流量。
