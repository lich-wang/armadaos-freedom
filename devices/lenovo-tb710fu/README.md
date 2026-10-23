# 联想小新 Pad Pro GT

ArmadaOS Freedom 统一内核与 kShimC 启动菜单对小新 Pad Pro GT 的适配。本页记录 TB710FU 的功能状态、已知问题、所需固件和开发入口。

| 项目 | 配置 |
|---|---|
| 型号 | TB710FU（小新 Pad Pro GT，3200×2000 120 Hz） |
| SoC | Qualcomm SM8650（骁龙 8 Gen 3，`qcom,pineapple`） |
| 设备树标识 | `lenovo,tb710fu`、`qcom,sm8650` |
| 内核 | ArmadaOS Freedom 统一 Linux 7.2.6 |
| 引导 | kShimC 菜单放在 boot_a，与原厂 Android 共存；Bootloader 未解锁 |
| 已验证的用户空间 | SteamOS（SteamOS-ARM-Port 的 sm8650 镜像，装在 UFS 上）；**ArmadaOS 镜像尚未在本机验证** |

## 功能状态

以下为统一内核（本仓库 `packages/kernel` 构建产物）在本机上的实测结果。

| 功能 | 当前状态 |
|---|---|
| kShimC 启动菜单 | 显示、音量／电源键选择、超时默认项正常；gzip 压缩的 boot（解压后约 109 MB）被 ABL 接受 |
| Android 启动 | 菜单进入原厂 Android（HyperOS）：`verifiedbootstate=green`、`locked`，Magisk 正常 |
| 显示 | NT36532 双 DSI + DSC，3200×2000@120，msm 原生驱动 |
| GPU | Adreno 750，Mesa freedreno／Turnip；频率 231–903 MHz；IFPC 关闭 |
| 触屏与手写笔 | NT36532 触摸正常；Lenovo Tab Pen Plus 压感、倾斜、按键正常 |
| 扬声器 | 4 颗 AW882xx 功放经 TDM 出声，左右声道正常 |
| WiFi | WCN7850（ath12k），5 GHz 下载实测 4–11 MB/s |
| 蓝牙 | 使用本机地址（来自 DT `local-bd-address`） |
| 电池与充电信息 | pmic-glink／battmgr 正常上报 |
| USB | 作为设备端（USB NCM 网络）正常 |
| 游戏 | Steam 游戏模式；Proton ARM64 游戏可进入主菜单 |

## 已知问题与待完成项

- **用户空间：** 只在 SteamOS 上验证过。ArmadaOS（bootc／OSTree）需要能挂载 OSTree 部署的 initramfs 和引导同步，尚未适配。
- **USB 网络：** 重启后偶尔出现 USB 设备已枚举、但 macOS 不建立 NCM 网卡的情况，插拔一次数据线即可恢复，原因未查清。OTG 主机模式未测试。
- **休眠：** 统一内核下的 s2idle 睡眠／唤醒尚未验证。
- **音频：** 只验证了扬声器。耳机、麦克风未测试。前端必须使用 S16：24 位输入会让 ADSP 的音频处理出错。
- **WiFi／显示的板级变通：** 部分补丁来自原移植项目的调试过程（MHI 轮询、DSI 控制器寄存器、PHY 时序等），按 `lenovo,tb710fu` 隔离，只在本机生效。是否都必要尚未逐项验证，后续可以继续精简。
- **视频编解码（iris）、相机、外接显示（DP）：** 未启用。
- **固件：** 设备专用固件需要从本机分区提取，本仓库不提供，见下文。

## 内核与启动

TB710FU 与 SM8650 掌机、Y700 四代和五代共用 [`packages/kernel`](../../packages/kernel/) 的统一内核。板级行为全部按 `lenovo,tb710fu` 或专用 compatible 匹配，不改变其它机型：

| 补丁 | 内容 |
|---|---|
| `0224`–`0225` | SY7758 背光：跟随芯片（`silergy,follower`），本机关闭升压突发模式 |
| `0226` | NT36532 WQHD 双 DSI DSC 面板驱动 |
| `0227`–`0229` | msm DSI：本机的双 DSI 命令触发口、ABL 留下的控制器与 PHY 状态、DSC 宽度取整 |
| `0230` | A750 目录项：本机不启用 IFPC（开启后 GPU 会冻结） |
| `0231` | NT36532 SPI 触摸与手写笔厂商驱动，compatible 为 `novatek,nt36532-ts-spi` |
| `0232` | 蓝牙：使用 DT 中的本机地址 |
| `0233`–`0235` | WCN7850：上电复位脉冲、MHI 上电、ath12k 变通 |
| `0236`–`0242` | 音频：上游 TDM 时隙辅助函数（回移植）、q6apm TDM DAI、TDM 输出端点、4 声道上混与声道映射、`lenovo,tb710fu-sndcard` 声卡 |

板级 DTS [`sm8650-lenovo-tb710fu.dts`](../../packages/kernel/dts/sm8650-lenovo-tb710fu.dts) 原样取自 MeteoricmeteorLL/tb710fu-linux 的固定提交 `16e800d4f6e5cf4a8517900a9e11eec0ebc91bd3`（`kernel/sources/arch/arm64/boot/dts/qcom/`）。本项目的改动在 [`sm8650-lenovo-tb710fu.dts.patch`](../../packages/kernel/dts/sm8650-lenovo-tb710fu.dts.patch) 中：kShimC framebuffer 模板、扬声器（AW882xx、TDM 引脚、声卡）、GPU 903 MHz 档位、手写笔、本机 ADSP/CDSP 固件路径，去掉原移植的调试保留区和其他机器的蓝牙地址，并把注释改为英文。原文件没有 SPDX 行，本补丁也未添加。

内核配置见 [`armada-kernel.config.overrides`](../../packages/kernel/config/armada-kernel.config.overrides) 中的 TB710FU 一节。

扬声器功放使用统一构建的 out-of-tree [`aw882xx`](../../packages/kernel/out-of-tree/aw882xx/README.md)（与五代相同的 0x2308 芯片），DT 中为 `awinic,aw882xx_smartpa`。

引导构建见 [TB710FU 引导说明](boot/README.md)。kShimC 的 TB710FU 支持在共享源码中：SM8650 的启动画面读取（ABL 用 4 个 VIG 管线拼接扫描输出）、跳过 size 为 0 的保留内存节点、`qcom,pineapple` 重启白名单，以及交接前清理只读的 WB 映射；菜单配置为 `configs/tb710fu_android_defconfig`。**TB710FU 的 boot 镜像不能刷到其它机型，反之亦然。**

## 固件

以下文件需要从本机的 Android 分区或 linux-firmware 中取得，放到根文件系统的 `/usr/lib/firmware/`：

| 路径 | 来源 |
|---|---|
| `qcom/sm8650/xiaoxin/gt/adsp.mdt`、`adsp.bNN`、`adsp_dtb.mdt`… | 本机 `/vendor/firmware_mnt/image`（ADSP） |
| `qcom/sm8650/xiaoxin/gt/cdsp*.mdt`… | 同上（CDSP） |
| `qcom/sm8650/xiaoxin/gt/gen70900_zap.mbn` | 本机 `/vendor/firmware`（GPU zap） |
| `qcom/gen70900_sqe.fw`、`qcom/gmu_gen70900.bin` | linux-firmware 或本机 `/vendor/firmware` |
| `novatek/novatek_nt36532_fw.bin` | 本机 `/vendor/firmware/novatek_ts_fw.bin` |
| `aw882xx_acf.bin` | 功放配置，来自 tb710fu-linux 的 board-root |
| `qcom/sm8650/Lenovo-TB710FU-tplg.bin` | tb710fu-linux 的 AudioReach 拓扑，其中唯一的 I2S 输出模块（`0x0700100A`）需改为 TDM 输出模块（`0x0700100E`） |
| `ath12k/WCN7850/hw2.0/{amss,board-2,m3}.bin` | linux-firmware |
| `qca/hmtbtfw20.tlv` 等 | linux-firmware（蓝牙） |

提取与修改拓扑的脚本见 [lich-wang/tb710fu-hyperos-steamos](https://github.com/lich-wang/tb710fu-hyperos-steamos)（`tools/collect_firmware.sh`、`tools/patch_tplg.py`）。

## 用户空间所需设置

- **WiFi：** `options ath12k board_name="bus=pci,vendor=17cb,device=1107,subsystem-vendor=17cb,subsystem-device=3378,qmi-chip-id=2,qmi-board-id=255"`，用于匹配 board-2.bin 中的条目。
- **扬声器路由与功放：** 声卡没有 UCM 配置，使用 pro-audio。开机后执行：

  ```sh
  amixer -c 0 cset name='SECONDARY_TDM_RX_0 Audio Mixer MultiMedia1' 1
  for i in 0 1 2 3; do amixer -c 0 cset name="aw_dev_${i}_switch" 1; amixer -c 0 cset name="aw_dev_${i}_monitor" 0; done
  amixer -c 0 cset name=aw_dev_0_volume 10; amixer -c 0 cset name=aw_dev_1_volume 10
  amixer -c 0 cset name=aw_dev_2_volume 0;  amixer -c 0 cset name=aw_dev_3_volume 0
  ```

  功放音量与 Android 下相同（0x34/0x35 衰减 21 档，0x36/0x37 衰减 11 档）。
- **PipeWire：** 输出 `alsa_output.platform-sound.pro-output-0`，`audio.format = "S16LE"`、48 kHz、2 声道。建议关闭空闲挂起：每次恢复都会重新启动 4 颗功放，偶尔会锁不上 TDM 时钟。

## 源码与来源

| 组件 | 来源 |
|---|---|
| 板级 DTS、面板／触摸／WiFi／DSI 变通 | [MeteoricmeteorLL/tb710fu-linux](https://github.com/MeteoricmeteorLL/tb710fu-linux) `16e800d4f6e5cf4a8517900a9e11eec0ebc91bd3`；面板与触摸的点亮工作来自 [SpendyYT](https://github.com/SpendyYT) |
| NT36532 触摸驱动 | Novatek 厂商驱动（GPL-2.0-or-later），经上述项目移植 |
| TDM 时隙辅助函数 | 上游 Linux `1e844ecbc9cb`、`0a9e00d5ebdf`（原作者署名保留在补丁中） |
| TDM DAI 操作 | 参照上游 Linux `4d0840175893`，按本树（无 MI2S 时钟控制）改写 |
| TDM 端点参数 | 在本机 HyperOS 上抓取 AudioReach 用户空间实际下发的参数 |
| kShimC、DualBootKernelPatcher | 与五代共用，见[五代组件来源](../lenovo-tb323fu/docs/SOURCES.md) |
