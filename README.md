# RK3588 灵足五路 USB CAN Hub 配置与诊断

记录 Ubuntu 22.04 ARM64 上接入 RobStride（灵足时代）五路 USB-CAN Hub 的实际配置，并提供可复用的诊断工具。验证日期：2026-10-21。

**当前已完成五路 USB 设备访问与五路静默内部回环；通过 Hub 与外部电机通信仍未成功。没有下载或刷写固件，没有安装内核 `gs_usb.ko`，Brainstem 的 USB 传输集成尚未完成。**

## 已经做了什么

| 项目 | 实际结果 |
| --- | --- |
| USB 枚举 | 发现 5 个 `1d50:606f`，名称为 `candleLight USB to CAN adapter` |
| USB 能力读取 | 5/5 成功；原始 `fw_version=2`、`hw_version=1` |
| 静默内部回环 | 5/5 收到完全匹配的 RX 数据，随后停止各适配器 |
| 外部 CAN 身份查询 | 1 Mbps；5 路均出现 ACK 错误，未收到电机身份应答 |
| 内核驱动 | `CONFIG_CAN_GS_USB` 未启用，`modinfo gs_usb` 找不到模块 |
| 当前访问方式 | Python → gs-usb → PyUSB → libusb → Hub 原有固件 |
| 原生 SocketCAN 接口 | 此方案不会新增 `canX` |
| 固件操作 | 沿用设备现有固件；未下载或刷写 `.bin` / `.hex` 固件 |

USB 回显仅表示 USB 传输反馈；内部回环验证控制器内部收发。两者都不能证明外部 CAN 收发器、线缆或电机已连通。

## 快速开始

在 RK3588 的 Ubuntu 系统上执行，Python 3.10 为本次记录的版本。新的虚拟环境安装流程见 [安装与实际部署](docs/installation.md)。

```bash
sudo apt-get update
sudo apt-get install python3-venv libusb-1.0-0 usbutils
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# 只读取 USB 信息和能力，不启动 CAN 控制器
sudo .venv/bin/python scripts/usb_can_probe.py inventory --output results/inventory.json

# SILENT + 内部 LOOPBACK，不请求向外部 CAN 总线发送
sudo .venv/bin/python scripts/usb_can_probe.py loopback --output results/loopback.json

# 以 inventory 输出的 USB 序列号选择已经接线的通道
# 会启动 CAN、发送电机身份查询；运行前停止占用适配器的其他程序
sudo .venv/bin/python scripts/usb_can_probe.py identity \
  --serial YOUR_USB_SERIAL --output results/identity.json
```

`--serial` 不填写时检查所有 `1d50:606f` 适配器；序列号排序不代表 Hub 面板端口编号。物理端口与 USB 序列号的对应关系仍待逐口确认。原主板的 CAN1～CAN6 丝印、Linux `canX`、新 Hub 的物理端口是三套编号，不能混用。

身份工具只查询候选 ID `1、2、3、4、127`，不是全地址扫描。出现 CAN 错误或缺少 USB 回显时，会结束当前短接收窗口并停止该通道后续查询。因此无应答不能等同于“没有任何电机”。脚本不发送使能、运动、零位、标定或改 ID 指令。

退出码：`0` 为所选检查满足条件；身份查询至少收到一条身份应答且无记录错误。`1` 为设备、通信、回环或清理错误；`2` 为身份查询未见应答且无记录错误。`0` 也不代表找齐所有预期电机，必须检查 JSON 中每路 `responses`、`completed` 和 `stop_reason`。

## 文档与资料

- [安装与实际部署](docs/installation.md)：安装版本、离线下载、实际目录、固件与驱动的区别。
- [诊断与接线](docs/diagnostics.md)：查询协议、ACK 错误、终端电阻、通道映射、Brainstem 后续工作。
- [验证记录](docs/verification.md)：实际硬件证据、脚本整理后的离线验证范围。
- [官方与上游参考](docs/references.md)：灵足官方手册、SDK、Linux 驱动与固件源码链接。
- [脱敏验证数据](evidence/)：删除设备序列号、启动 ID 等环境标识后的记录。
- [下载校验清单](manifests/runtime-wheels.json)：实际使用的六个 wheel 文件名和 SHA256。

本仓库是项目接入记录，不是灵足官方驱动发布。第三方代码和手册通过链接引用；不包含固件、原始日志、登录凭据或第三方 wheel 二进制。
