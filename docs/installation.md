# 安装与实际部署

## 固件 驱动与用户态库

| 层级 | 作用 | 本次处理 |
| --- | --- | --- |
| Hub 内部固件 | 在适配器 MCU 上运行，处理 USB 与 CAN | 沿用原有固件，读取原始版本字段 `2` / `1`；无法据此推断具体厂商发布版本 |
| Linux `gs_usb` 内核驱动 | 把兼容 USB 适配器注册为 SocketCAN 网络接口 | 当前内核没有启用，未编译或安装 |
| Python `gs-usb` 库 | 在用户态实现 gs_usb 协议 | 安装 `0.3.1`，通过 PyUSB/libusb 访问 |
| `python-can` | Python CAN 接口抽象及 gs_usb 后端 | 安装 `4.6.1`；本仓库探测脚本直接使用底层 gs-usb |

缺少板厂内核源码不会阻止所有使用方式：本次已经验证用户态 libusb 路径可用。若需要原生 SocketCAN，则仍需要兼容的内核模块或包含该驱动的内核。不能把其他发行版或其他内核版本的 `gs_usb.ko` 直接复制过来使用。

实际系统为 Ubuntu 22.04.5 ARM64、Linux 6.1.84（Talowe 平台），Python 3.10。系统已有 `/lib/aarch64-linux-gnu/libusb-1.0.so.0`。内核配置显示 `# CONFIG_CAN_GS_USB is not set`，未找到 `/lib/modules/6.1.84/build` 与可用配套内核头文件。此次没有修改内核或设备树。

## 已安装的软件

```text
gs-usb             0.3.1
python-can         4.6.1
pyusb              1.3.1
wrapt              1.17.3
packaging          26.3
typing_extensions  4.16.0
```

原部署从电脑下载六个 CPython 3.10 / ARM64 兼容 wheel，经 SHA256 校验后离线解包到隔离目录：

```text
/userdata/brainstem-usb-can-runtime/
├── python
└── gs-usb-0.3.1-python-can-4.6.1/
    └── site-packages/
```

`python` 是设置隔离包搜索路径的启动包装器。没有进行全局 pip 安装。原探测脚本也保存在该 runtime 目录。本仓库提供的是整理后的统一 CLI，不会自动覆盖原板上部署。

下载内容为 Python wheel、官方说明书和参考源码；**没有下载或刷写 Hub 固件**。`candleLight_fw` 仅作为协议与固件项目参考，不能把通用构建直接视作五路 Hub 的适配固件。

## 新环境安装

推荐使用 README 的 venv 安装步骤，保持系统 Python 与项目依赖隔离。这是新的复现流程，与原板上离线解包方式不同。

需要离线安装时，可在联网电脑执行以下跨平台下载，再把仓库和 `wheelhouse` 复制到目标板：

```bash
python -m pip download --only-binary=:all: \
  --platform manylinux2014_aarch64 --python-version 310 \
  --implementation cp --abi cp310 \
  -r requirements.txt --dest wheelhouse
```

核对 [原下载校验清单](../manifests/runtime-wheels.json)。版本相同但平台 tag 或文件名不同的 wheel 可能有不同哈希；不要将清单中的哈希当作所有平台的通用哈希。

目标板需先具备 `python3-venv` 和 `libusb-1.0-0`，再执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheelhouse -r requirements.txt
.venv/bin/python -m pip check
```

本仓库不自动安装系统服务、不自动启动电机控制、不修改 udev 或驱动绑定。示例使用 sudo 获取 USB 访问权限；生产部署可按现场权限规则配置 USB 设备访问组。

## 与 SocketCAN 及 Brainstem 的关系

官方手册的 Linux 路径使用 SocketCAN / can-utils，前提是内核驱动可用。当前用户态方案直接打开 USB 设备，并不把它们注册为 `can0` 等网络接口，所以不能直接用 `candump` 查看这些 USB 通道。

当前 Brainstem 的 `pcan/lib/src/socketcan.dart` 使用原生 `AF_CAN`。安装 `python-can` 并不会自动为 Dart 程序增加 USB 传输后端。后续可选择：补齐匹配内核的驱动，或实现 USB 用户态后端/桥接；均需重新验证收发、断线恢复和控制周期。尚未测得可用于 1 kHz 闭环控制的端到端性能。
