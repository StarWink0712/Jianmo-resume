# M1 候选资源与许可清单

日期：2026-10-01。用途：实验来源追踪，不是已完成的再分发法律审查。本轮未发布运行时安装包。

后续更新：已生成本地专用运行时测试包，未公开发布。其许可原文存于包内 `licenses/` 与 `tex/licenses/`，构建说明见 [专用运行时](managed-runtime.md)。

## 当前字体更新

M2 已改用 Noto Sans CJK SC 2.004 普通体/粗体及 Noto Sans 2.008 西文四字形，替换下文首轮实验中的 Fandol/Termes 正文字体。
来源为 `notofonts/noto-cjk` 的 `Sans2.004` 标签；未修改的 OTF、原始 SIL OFL 1.1 许可和 Adobe 版权说明保留在 `assets/fonts/`。
二进制内 `OS/2.fsType=0`；按 OFL 随软件分发与嵌入 PDF，不单独销售字体。大小/哈希锁定及细节见 [字体资源](../../assets/fonts/README.md)、[统一字体](../m2/fonts.md)。
西文字体取自 `notofonts/noto-fonts` 的固定提交，原始 OFL 单独存为 `NotoSans-LICENSE`；Google/Noto 版权保留在文件元数据及原始许可中。
新包保留 Latin Modern 的初始化依赖及许可，但实际输出字体检查只允许 Noto。
不分发 PingFang/Avenir 等苹果系统字体。以下 Fandol/Termes 表格和大小是历史记录，不是当前包字体清单。

## 第二轮新增资源

| 资源 | 用途 / 许可记录 |
| --- | --- |
| PyInstaller 6.22.3 | 冻结 Python 程序；随包保留 COPYING.txt（GPL 与 bootloader 分发例外），不是应用必须采用 GPL 的简单结论 |
| Python 3.14.7 | 包内含解释器与必要标准库，保留 Python LICENSE.txt；系统版本兼容未跨机器验证 |
| Latin Modern 四个 Roman 10 字体 | `article` 和 `fontspec` 初始化时使用；GUST Font License，保留 LICENSE、README、MANIFEST；补齐了首轮 recorder 未完整捕获的启动依赖 |
| OpenSSL 3 的动态库 | Python SSL 依赖，Apache-2.0；保留 LICENSE/AUTHORS |
| Zstandard 动态库 | Python 标准库压缩依赖；保留 BSD LICENSE 和 GPL COPYING，最终分发选择需记录 |
| mpdecimal 动态库 | Python decimal 依赖，BSD-2-Clause 原文保留 |

Python 包的实际版本与许可文件路径见包内 `licenses/packages.json`；每个实际文件及符号链接见 `runtime.json`。这补充了来源与声明，但**不是完整 SBOM/静态链接源码审计**。XeTeX 内部静态库、预生成格式、部分宏包与发行源对应关系、项目发布许可证仍需在公开分发前审核。

PyInstaller 对本地可执行程序使用 ad-hoc 签名以满足加载要求，这不等于 Apple Developer ID 签名或公证。不能据此承诺从网页下载后不会被 Gatekeeper 拦截。

## 已查阅的字体与映射

| 资源 | 版本 / 来源 | 许可与记录 |
| --- | --- | --- |
| FandolSong Regular/Bold、FandolKai Regular | Fandol 0.3；本机 TeX Live `texmf-dist/fonts/opentype/public/fandol/` | README 声明 GPL + GPL font exception，COPYING 含 GPL 与字体嵌入例外 |
| TeX Gyre Termes Regular/Bold/Italic/BoldItalic | 家族 README 2.004；本机 `fonts/opentype/public/tex-gyre/` | GUST Font License，基于 LPPL 1.3c 或更新版本；复制 LICENSE、README、MANIFEST |
| Adobe-GB1-UCS2 | 8.004；Adobe 1990-2019；本机 `adobemapping` | BSD-3-Clause 条款位于文件头；复制整个文件，嵌入 PDF 时也保留完整头部声明 |

Fandol 的嵌入例外说明：将未修改字体的全部或部分嵌入文档，不会仅因为嵌入而使该文档受 GPL 覆盖。**这不等于字体二进制再分发没有义务**；打包字体或修改/子集化字体文件时仍须核查相应许可、源代码与声明要求。实验未修改原始字体文件，PDF 内由排版引擎正常嵌入。

复制的原文位于 `.m1-runtime/licenses/`；映射声明位于 `.m1-runtime/cmaps/Adobe-GB1-UCS2`。逐文件 SHA-256、来源相对路径和大小记录在 [runtime-inputs.json](runtime-inputs.json)。这里只记录本次实际资源的身份，**不是对未来下载内容的信任签名**。

CMap：231,844 字节，SHA-256 `01ba1aadce97dd9ce49e087aaf2f729e344ee5051f030be888cb5c4fd3827f6c`。7 个字体共 19,081,960 字节。TeX Gyre 包集合元数据版本 2.501 与 Termes 家族 README 的 2.004 是不同粒度，不混为同一版本。

M0 的 Noto/思源字体仍是候选。本轮使用现有 Fandol 以验证编译链路，不构成最终字体选型；若分发或 Unicode 兼容成本过高，应对照 Noto/思源重新测量，而非绕过许可证。

## 引擎和主要宏包

下表来自本机只读 `tlmgr info --only-installed`，不等于逐一查完源代码和所有依赖的原始许可。`TL revision` 固定本次清点身份；不是可复现发布锁文件。

| 包 | TL revision / 版本 | catalogue 许可 |
| --- | --- | --- |
| xetex | 77830；引擎 0.999998 | x11 |
| dvipdfmx | 78409 | gpl |
| fontspec | 77682 / 2.9g | lppl1.3c |
| xecjk | 77682 / 3.9.1 | lppl1.3c |
| enumitem | 77682 / 3.11 | mit |
| geometry | 78315 / 6.0 | lppl1.3c |
| needspace | 77682 / 1.3e | lppl1.3c |
| hyperref | 77682 / 7.01p | lppl1.3 |
| graphics（包含 graphicx） | 78282 | lppl1.3c |
| latex | 76924 | lppl1.3c |
| fandol | 37889 / 0.3 | gpl，实际 README 另有字体例外 |
| tex-gyre | 68624 / 2.501（集合） | gfl |
| adobemapping | 66552 | bsd |

标准 PDF 的 `.fls` 记录 55 个 TeX 输入文件。该列表不保证包含所有动态库、输出驱动、字体解析库、可执行程序与系统运行依赖，不能据此直接打包一个“已审计最小引擎”。

## Python 实验依赖

依赖版本见 [requirements-m1.txt](../../requirements-m1.txt) 和 [requirements-dev.txt](../../requirements-dev.txt)。许可来源为本地 dist-info 元数据；Markdown 两项因 License 字段为空，另查了安装包中的原始 LICENSE。

| 资源 | 版本 | 许可 |
| --- | --- | --- |
| markdown-it-py | 4.0.0 | MIT，原文已查阅 |
| mdurl | 0.1.2 | MIT，含 node.js/Joyent 来源声明，原文已查阅 |
| pypdf | 6.1.1 | BSD-3-Clause |
| Pillow | 12.0.0 | MIT-CMU；wheel 内第三方库仍需单独审计 |
| jsonschema / jsonschema-specifications | 4.25.1 / 2025.4.1 | MIT |
| attrs / referencing / rpds-py | 25.3.0 / 0.36.2 / 0.27.1 | MIT |
| typing_extensions | 4.15.0 | PSF-2.0 |

Python 解释器、pip 和未来前端构建依赖也应进入最终安装包 SBOM。本轮模板为项目自建，但项目代码的发布许可证仍待确定。

## 发布前必须补齐

固定最终引擎/字体路线，逐项确认二进制与动态库许可证、源码或源码提供义务、完整许可原文和版权声明；验证字体子集/修改规则；将实际随包资源与 SBOM 和哈希清单对应。不能仅凭“免费使用”“TeX Live 已装”或 catalogue 的一个短标签签署 LIC-01。
