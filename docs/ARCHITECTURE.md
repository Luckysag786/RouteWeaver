# 架构与数据流

## Windows

```text
代理感知应用/浏览器
        |
        v
127.0.0.1:<gateway-port>  路由织网
        |
        +-- 规则命中/未命中决策 --> 直连目标站点（国内出口）
        |
        +-- 规则命中/未命中决策 --> 原第三方 HTTP/SOCKS5 代理（例如 127.0.0.1:7890）
                                      |
                                      v
                                  VPN 公网出口
```

网关从 TCP 连接表读取连接到本地监听端口的客户端 PID，再解析可执行文件路径。规则引擎同时匹配进程路径/文件名和规范化域名。所有决策写入内存活动日志，UI 不把推断结果展示为公网 IP。

系统代理接管是事务式的：启用前把 `ProxyEnable`、`ProxyServer`、`ProxyOverride`、`AutoConfigURL` 保存到用户配置目录和注册表所有权标记；停用时按原类型和值恢复。若上次异常退出，下次启动会先提示并可恢复。

## Android

Android 应用不启动第二个 `VpnService`，避免系统强制断开用户已有的第三方 VPN。它保存与桌面一致的两种规则、检测当前 VPN 传输能力、显示真实公网 IP、发现已安装 VPN，并可导出 JSON 配置。若提供商声明 `com.routeweaver.APPLY_SPLIT_RULES` 接口，APK 会以显式广播交接模式、包名和域名；否则复制清单并启动提供商应用。最终的系统分流仍必须由当前 VPN 提供商的 `VpnService.Builder.addAllowedApplication/addDisallowedApplication` 完成，或在已 root 设备上使用针对具体 ROM/提供商验证过的网络策略。
