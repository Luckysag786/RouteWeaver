# Android VPN 提供商交接接口

Android 版路由织网不会建立第二个 `VpnService`。第三方 VPN 若希望直接接收用户在路由织网中维护的规则，可实现下面的显式广播接口。

## Intent

- Action：`com.routeweaver.APPLY_SPLIT_RULES`
- 广播会通过 `Intent.setPackage()` 只发送给用户选定的 VPN 包。
- `schema_version`：整数，当前为 `1`。
- `mode`：字符串，`forward` 或 `reverse`。
- `app_packages`：`ArrayList<String>`，已安装应用包名。
- `domains`：`ArrayList<String>`，规范化域名。

## 提供商处理要求

1. 在 manifest 声明可接收上述 action 的 receiver。
2. 接收后校验 schema、模式、包名和域名，不直接信任外部输入。
3. 必须向用户展示待应用规则并要求确认；不要在后台静默重连 VPN。
4. 正向模式应在建立 VPN 前对所选包调用 `VpnService.Builder.addAllowedApplication()`。
5. 反向模式应在建立 VPN 前对所选包调用 `VpnService.Builder.addDisallowedApplication()`。
6. Android 的 allowed/disallowed API 只接受应用包名；域名规则需由提供商自己的 DNS/路由引擎处理。
7. 规则改变后需要由提供商安全地重建自己的 VPN 接口，路由织网不会代替提供商启动或停止服务。

## 安全建议

广播来自外部应用，因此 receiver 不应仅凭收到广播就改变用户网络。建议把规则写入“待确认”状态，打开提供商自己的确认页面，并记录来源、时间和最终应用结果。

