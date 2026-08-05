# RouteWeaver 1.3.1：让需要的应用走代理，其余继续直连

这是路由织网首次公开发布版本，面向同时使用国内网络与国外服务、又不希望全局代理拖慢所有软件的用户。

## Windows 版

- 正向映射：仅指定应用/网站走现有 VPN/代理。
- 反向隔离：默认走代理，指定国内应用/网站改为直连。
- 从 EXE 文件、运行进程和已安装应用三种来源添加程序。
- 规则支持修改、查重、启停、批量删除和快捷操作。
- 真实出口 IP/地区验证、连接活动和诊断。
- 系统代理事务式接管与恢复、开机启动和托盘运行。

推荐普通用户下载 `RouteWeaver-Windows-Setup-1.3.1.exe`；免安装测试可使用 `RouteWeaver-Windows-1.3.1.exe`。

## Android 版

Android APK 是规则管理、出口验证和兼容提供商交接伴侣。受 Android 单一 `VpnService` 规则限制，它不会冒充能够透明接管另一个第三方 VPN。当前 APK 使用 Debug 侧载签名，仅供测试与社区协作。

## 验证

- Python 自动化测试：27 项通过。
- Android：Java 单元测试与 Debug APK 构建通过。
- 三轮真实链路复测通过，覆盖正向/反向、应用/网站、HTTP/SOCKS5。

## SHA-256

```text
894A88533BBB96892F66308F7EA0159F31ABDC644F9F19822A31909EF0C63329  RouteWeaver-Windows-1.3.1.exe
9D1A74AD135B23A5749D526E3DB276E33D1366A80D402174A092F5F54469B7E2  RouteWeaver-Windows-Setup-1.3.1.exe
B630A0B20FB08E8603235EC2CF4F9B7768F23A8A8BD6FD3AE7BA394F091D1E85  RouteWeaver-Android-1.2.0-debug.apk
```

请在所在地法律、单位网络规范及相关服务条款允许的范围内使用。本项目与任何第三方 VPN/代理品牌均无隶属或背书关系。
