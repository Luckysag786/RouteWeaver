# Android 版

Android 包与桌面版共用“正向映射/反向隔离”的规则概念，提供应用/域名规则、VPN 状态、真实公网 IP、物理网络绑定出口测试、已安装 VPN 发现、显式规则交接、JSON 导入导出和 VPN 设置入口。

它刻意**不声明 `VpnService`**：Android 每个用户/工作资料只能运行一个 VPN 服务，若本应用申请并建立第二条隧道，系统会停止用户当前的第三方 VPN，违反本项目“不关闭、不修改原 VPN”的约束。

因此，此 APK 是安全的规则与验证伴侣；规则的系统级应用入口必须由当前 VPN 提供商在自己的 `VpnService.Builder` 中调用 `addAllowedApplication` 或 `addDisallowedApplication`。APK 会发现真正声明 `VpnService` 的应用；提供商若实现 `com.routeweaver.APPLY_SPLIT_RULES` 广播接口即可直接接收规则，否则 APK 会复制规则清单并打开提供商应用。UI 会如实展示这一兼容性状态，不会显示虚假的“已应用”。

构建命令由仓库根目录 `scripts/build_android.ps1` 封装。
