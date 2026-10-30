# Z6 Firmware Toolkit

离线分析、文档与补丁工具链，对象是尼康 **Z6 C 3.80** 固件包（`Z_6_0380.bin`）。

Offline analysis, documentation and patch tooling for the Nikon **Z6 C 3.80** firmware package.

---

## 这个仓库里有什么 / 没有什么

| 有 | 没有（也永远不会提交） |
|---|---|
| 解密 / 解析 / 打补丁的源码（`z6fw/`） | ❌ 任何尼康固件（`*.bin` / `*.exe`） |
| 固件格式、地址簿、方法论文档（`docs/`） | ❌ 解密后的镜像或 EG 模块 |
| 可复现的检查脚本（`scripts/`） | ❌ XOR 密钥表（`key.json`） |
| | ❌ 任何打补丁后的产物 |

**你需要自备：** 官方固件包，以及由公开工具自行恢复的密钥表。
本仓库不含、也不再分发任何尼康版权内容或派生密钥。

---

## 这是什么

`Z_6_0380.bin` 是 34,923,366 字节的加密容器，解开后是四个独立程序：

| 模块 | 大小 | 说明 |
|---|---|---|
| `ex1620_037000.bi` | 512 KB | ExMCU，Cortex-M |
| `_tpj01_v140.bin` | 57 KB | 第二单片机 |
| `eg1620_038000.bi` | 33.5 MB | **Engine**（ARM926 + µT-Kernel），主要目标 |
| `vr1620_010200.bi` | 839 KB | VR/IBIS 防抖 |

三个关键事实：

1. **加密是位置无关的异或**（三张 256 字节表，keystream 周期 16 MiB），密钥可由多机型交叉推出。
2. **补丁只需改 EG 一个模块**，用等长字节替换；模块级只需 CRC，因此绕过整包签名。
3. **风险不在解密，在投递**——相机是否接受独立 EG 模块、失败能否恢复，尚无公开验证。

---

## 快速开始

```bash
pip install -r requirements.txt

# 把官方固件与自行生成的 key.json 放到工作目录
python -m z6fw info        # 读出 stock EG、模块清单、预设目标尺寸
python -m z6fw selftest    # 零改动重打包必须与输入字节一致
python -m z6fw probe       # 生成 CRC 故意损坏的通道探路文件
python -m z6fw aspect --preset aspect-21x9
```

`python scripts/inspect_firmware.py <workspace>` 会一次跑完所有基础测量
（文件身份、熵、容器结构、基址指纹、尺寸表、源码模块名），用来验证文档里的每个数字。

---

## 三个目标的状态

| 目标 | 状态 |
|---|---|
| 开发文档（供后来者） | ✅ `docs/Z6_固件开发手册.md` |
| 21:9 与 Max32 画幅 | 🟡 尺寸表补丁完成并自检；**裁切窗口未改，禁止上机** |
| 快门声音 | 🔴 调查完成：Z6 无 SD 播放通路，需新增音频链路，本轮不实现 |

画幅预设的目标尺寸：

| 预设 | L | M | S |
|---|---|---|---|
| `aspect-21x9` | 6048×2592 | 4528×1940 | 3024×1296 |
| `aspect-max32` | **6048×4000** | 4528×2996 | 3024×2000 |

`aspect-max32` 的 L 档两条边均可被 32 整除（6048/32 = 189，4000/32 = 125）。

---

## ⚠️ 风险

- **当前画幅候选会得到压扁画面，不是裁切。** 传感器读取窗口由代码推导，
  只改输出尺寸表会让相机重采样现有 16:9 窗口。工具会打印醒目警告。
- **刷机可能变砖。** 上游公开记录里出现过装完功能异常、且"紧急恢复未验证"的情形。
- 更新过程中断电会损坏机身，只能返厂。
- 本仓库不提供任何刷机自动化，所有写操作都由人工在相机菜单里完成。

**先做通道探路**：`python -m z6fw probe` 生成只差 1 字节的文件，放到卡里点一次更新。
相机若报"文件不正确"，说明它确实会读独立 EG 模块且校验早于写入——这是继续的前提。
若完全无反应，则整条路线不成立。

---

## 致谢与来源 / Credits

这项工作建立在前人的公开成果之上。**特别致谢 `WonderLantern` 组织与其维护者**——
他们不仅公开了同为 EXPEED 6 的补丁方法，而且他们的 Z6 项目正是针对**同一份 C3.80 固件**
做的自定义快门声与长曝光工作。没有这些公开记录，本仓库无从开始。

| 项目 | 与本仓库的关系 | 其许可 |
|---|---|---|
| **[WonderLantern/WonderLantern-z6](https://github.com/WonderLantern/WonderLantern-z6)**<br>（原 `vic2349/Wonder-Lantern`） | **最直接的前辈项目。** 适用机型 Nikon Z6、基于 C3.80；实现自定义快门声，并把肩屏倒计时主体迁入卡载 `SLOWCORE.BIN`。本仓库目标 3 的可行性判断直接建立在此之上。 | Wonder Lantern Community License |
| **[WonderLantern/wonder-lantern-z30](https://github.com/WonderLantern/wonder-lantern-z30)**<br>（原 `RealCaCl2/z30-firmware-extensions`） | 同为 EXPEED 6。独立 EG 模块投递、等长字节替换 + expected 校验 + 尾部追加 + CRC 重算、复用原厂 16:9 槽位做自定义画幅——本仓库的补丁模型照此设计。 | MIT + Wonder Lantern Community License（14 个声音/画幅文件） |
| **[WonderLantern/nikon-fw-key-tool](https://github.com/WonderLantern/nikon-fw-key-tool)** | 容器布局、三表 XOR 与 2²⁴ 周期、`SHA1(body‖K8)` 头部摘要、由 padding 反推密钥的方法。本仓库不含其代码，密钥需自行用该工具恢复。 | GPL-3.0 |
| **[tylermcm/WonderLanternZ7](https://github.com/tylermcm/WonderLanternZ7)** | Z7 的实机记录，其中"最新结果：失败"与"紧急恢复未验证"是本仓库风险章节的主要依据。 | 见其仓库 |
| **[simeonpilgrim/nikon-firmware-tools](https://github.com/simeonpilgrim/nikon-firmware-tools)** | 更早的尼康固件容器社区工具，用于对照理解格式。 | MIT |

**本仓库不包含上述任何项目的代码。** 上表的许可是各项目的，不是本仓库的。

### 本仓库的许可划分

| 范围 | 许可 |
|---|---|
| **文档**（`docs/`、`README.md`、`NOTICE`） | **CC BY-SA 4.0** — 见 `LICENSE-docs` |
| **代码**（`z6fw/`、`scripts/`） | MIT — 见 `LICENSE` |

采用 CC BY-SA 4.0 是希望这些分析与文档能被自由转载、翻译和继续修订，
但署名必须保留、衍生作品须以相同方式共享。

并且本仓库与其致敬的上游项目一致：**免费分发，不收费、不设付费墙。**

用途限定：互操作性研究与个人学习。请遵守所在地法律，不要分发固件内容或派生模块。

