# 官方与上游参考

## 灵足官方资料

- [RobStride Product Information](https://github.com/RobStride/Product_Information)
- [五路 USB CANHUB 使用说明 V1.0](https://github.com/RobStride/Product_Information/blob/main/%E4%BA%A7%E5%93%81%E8%B5%84%E6%96%99/canhub/USB_CANHUB%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8EV1.0.pdf)
- [RobStride C++ 与 ROS 示例](https://github.com/RobStride/robstride_ros_sample)
- [RobStride Python SDK](https://github.com/ROBSTRIDE-DYNAMICS/Robstride-Dynamics-Python-SDK)

本次读取的官方手册 Git blob 为 `72cd44c1b4cfae34410cb7cbe83e28639e83ae6d`，PDF SHA256 为 `ed3bcddbc65d777144ded45916ddf480a291aaba1a46335b4cefb1ba331c09d1`。仓库仅提供来源链接，不重新分发手册。

五路 Hub 手册的 Linux 使用方式涉及 SocketCAN / can-utils、1 Mbps。旧款单口 CH340 / AT 指令适配器属于不同产品，不应套用其串口驱动或 AT 指令配置本次 `1d50:606f` 设备。

## 协议与软件参考

- [python-can gs_usb 后端](https://python-can.readthedocs.io/en/stable/interfaces/gs_usb.html)
- [用户态 gs_usb 库](https://github.com/jxltom/gs_usb)
- [Linux v6.1 gs_usb 驱动](https://github.com/torvalds/linux/blob/v6.1/drivers/net/can/usb/gs_usb.c)
- [candleLight 固件项目](https://github.com/candle-usb/candleLight_fw)

`stable` 文档及默认分支会更新，本次依赖版本以仓库 `requirements.txt` 和下载清单为准。固件项目链接不表示曾使用其固件刷机，也不保证任意构建与灵足五路 Hub 的硬件适配。
