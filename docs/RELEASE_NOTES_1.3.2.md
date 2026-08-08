# RouteWeaver 1.3.2：出口检测、链路稳定性与单实例安全更新

发布日期：2026-08-08

## 本次更新

- 公网 IP 检测由两个串行服务改为多服务并发容错。单个服务发生 TLS 提前断流、超时或限流时，健康服务可直接返回真实出口。
- HTTP CONNECT 在收到上游成功响应后才发送客户端 TLS 数据，避免部分本地代理重置提前发送的隧道数据。
- TCP 转发正确处理半关闭，客户端结束发送后仍会继续接收并排空服务端剩余响应。
- 自动识别覆盖 Windows 系统代理、RouteWeaver 启用前事务备份、PAC、WinHTTP、环回代理环境变量、已保存端口与常见本地代理端口。
- 自动保存上游协议、地址、端口、识别来源和更新时间；运行中重新识别不会把 RouteWeaver 自身网关误填为上游。
- 新增 Windows 命名互斥体。每个用户会话只能运行一个 RouteWeaver 实例，重复启动显示提示后退出；管理员提权重启流程可安全交接实例锁。

## 下载

- 推荐安装版：`RouteWeaver-Windows-Setup-1.3.2.exe`
- 免安装版：`RouteWeaver-Windows-1.3.2.exe`
- Android 规则伴侣：`RouteWeaver-Android-1.2.0-debug.apk`（本次未修改 Android 功能）

## 验证

- 34 项 Python 自动化测试通过。
- Windows 命名互斥体通过同进程及跨进程重复启动测试。
- 真实 HTTP 与 SOCKS5 上游出口检测通过；直连与 VPN 出口地址不同。
- 真实本地网关访问分别记录为 `direct` 与 `vpn`。
- PyInstaller 单文件程序和 Inno Setup 6.7.3 安装包构建成功。

## SHA-256

```text
00AC7556C68070272B482EDCFC2826370F513DA3625BAC17F9871A68C0539B87  RouteWeaver-Windows-1.3.2.exe
7A0D9F34F99D25EAF763CCA7B72091FC6846E998CE2C2478158A1AB8D2C375EF  RouteWeaver-Windows-Setup-1.3.2.exe
B630A0B20FB08E8603235EC2CF4F9B7768F23A8A8BD6FD3AE7BA394F091D1E85  RouteWeaver-Android-1.2.0-debug.apk
```

## 能力边界

Windows 后端继续覆盖遵循系统代理的 TCP/HTTP(S) 流量。UDP、QUIC、自建协议及明确忽略系统代理的应用，仍需要签名 WFP 驱动或应用自身的代理能力。
