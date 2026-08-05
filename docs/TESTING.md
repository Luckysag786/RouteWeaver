# 测试指南

## 自动化测试

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

## 系统代理事务测试

该测试会临时把当前用户的系统代理切换到测试网关，然后恢复测试前的完整值。请先保存工作，并确认没有另一实例正在管理系统代理。

```powershell
.\.venv\Scripts\python.exe .\scripts\proxy_transaction_test.py
```

## 真实上游分流测试

真实测试不会关闭或修改第三方代理客户端，但会向公网 IP 回显服务建立连接。必须显式提供已有本地代理端口，避免脚本携带开发者个人环境参数：

```powershell
$env:ROUTEWEAVER_UPSTREAM_HOST = "127.0.0.1"
$env:ROUTEWEAVER_UPSTREAM_PORT = "7890"
$env:ROUTEWEAVER_TEST_PROTOCOLS = "http,socks5"
.\.venv\Scripts\python.exe .\scripts\live_vpn_test.py
```

如果上游只支持一种协议，把最后一个变量设为 `http` 或 `socks5`。测试 JSON 写入被 Git 忽略的 `artifacts/`，公开结果前应删除公网 IP、本地端口、用户名和应用路径。
