# M1 专用运行时与安装验证

**当前可迁移启动流程：** 见 [源码启动与正式 TeX 基线更新](tex-baseline-update.md)。普通用户使用 `sh scripts/start-local.sh`；系统预生成的 `xelatex.fmt` 不再是跨机器校验基线，改为校验源文件并在项目中生成格式。下方早期体积/版本数据为历史记录，以当前 `managed-artifact.json` 和 `managed-results.json` 为准。

日期：2026-10-01。本轮按用户要求跳过干净 macOS 验收，不安装虚拟机、不使用另一台电脑。跳过不是通过，也不是整个产品已经可用。

**后续字体更新：** 新包版本为 `m1-local-20261001-noto-2.004`，改用随项目分发的 Noto Sans CJK SC。
当前哈希/大小和验证结果以 `managed-artifact.json`、`managed-results.json` 为准；下文第二轮旧测量表保留为历史记录。
当前 M2 已接入该运行时，但 M2 服务本身仍不在冻结安装包中。字体方案见 [统一字体](../m2/fonts.md)。

**后续样式更新：** 当前产物已推进至 `m2-style-20261001`，包含像素样式配置与彩色标题/分隔线渲染；25 项安装/隔离回归再次通过。新配置随冻结程序打包，没有新增宿主字体或宏包依赖。此前版本号和测量均为历史记录。

**整数控件更新：** 最新产物为 `m2-integer-style-20261001`，同步整数制 v3 样式、旧数据兼容转换及配置；25 项安装/隔离回归再次通过。完整 M2 服务仍未纳入冻结安装包。

## 交付内容

`output/runtime/` 包含本机构建的运行时压缩包、内嵌大小/SHA-256 的安装脚本及产物清单。它包含冻结的 Python 3.14.7 执行程序与依赖、XeTeX/xdvipdfmx、固定模板所需宏包、格式文件、字体和 CMap。安装和运行不需要另装 Python、Node 或 LaTeX；**构建**仍使用开发机现有的 TeX Live 和项目虚拟环境。

该包只用于当前 macOS arm64 的本地技术验证。未设置公开下载源、未做 Developer ID 签名/公证、未完成完整再分发审计；不能作为已经通过跨机器验收的公开发行版。不是任意 LaTeX 文档的通用发行版，也不是已接入网页的后端。

源码入口：[构建器](../../experiments/m1/build_runtime.py)、[安装器模板](../../scripts/install-runtime.sh.in)、[运行时自检](../../experiments/m1/packaged_cli.py)、[安装回归](../../experiments/m1/validate_managed.py)。

## 使用与复现

在项目根目录使用已生成的本地包，无需 Python：

```bash
/bin/sh output/runtime/install-runtime.sh --prefix "$PWD/.m1-build/local-install"
.m1-build/local-install/current/resume-runtime verify
.m1-build/local-install/current/resume-runtime self-test
```

不传 `--prefix` 时，默认安装到用户的 `~/Library/Application Support/LocalResumeM1`。不会修改 shell profile、PATH、全局 TeX 或用户简历数据。自检只处理打包的虚构样例，默认创建独立临时输出目录并打印报告路径；不是用户简历导入命令。

开发者重新构建和验证：

```bash
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m experiments.m1.build_runtime
.venv/bin/python -m experiments.m1.validate_managed
.venv/bin/python -m unittest discover -s tests -v
node --test tests/resume-library.test.cjs
```

构建要求 TeX 源文件与正式批准的 `runtime-inputs.json` 相符，并验证关联实验与审核记录。宿主格式缓存和机器定制配置不再复制；格式在受限环境中重新生成，并在打包前执行真实 PDF 自检。真实宏包/引擎源码变化按基线更新流程处理。原始字体/引擎及格式来源记录在包内 `tex/source-inventory.json`。构建锁防止两个构建同时覆盖产物；构建期间不要运行安装回归。

构建与回归产物均已加入忽略规则，不会把约百兆二进制、测试证书和作业日志默认纳入 Git。提交的源代码、文本报告和清单提供复现入口；这不是逐字节可复现构建或完整供应链锁定的声明。

## 安装行为

- 安装脚本固定预期大小与 SHA-256；先校验整个压缩包，才解包或执行其中程序。不信任旁边下载来的动态哈希。
- 在安装目录内创建独占锁与临时目录，解包后核对文件哈希、权限和内部符号链接；校验成功再切换 `current` 链接。
- 重复安装验证已有版本，旧版本目录保留；新包校验失败不覆盖当前指针，不修改旧版本或用户数据。
- 已安装版本损坏时明确失败，要求使用新的 `--prefix` 重装，不偷偷删除损坏目录中的未知文件。
- `--archive FILE` 支持指定本地压缩包；`--url HTTPS_URL` 仅接受与脚本内哈希完全一致的 HTTPS 包，并拒绝降级到 HTTP。
- 捕获正常退出/终止信号后清理临时目录和锁。断电或 SIGKILL 可能留下 `.install-lock`，需确认没有安装进程再人工清理；尚未实现自动恢复锁、空间预检或完整升级回滚。

当前安全解包依赖“构建器生成、哈希已固定且完整验证”的受信任归档；不是接受任意用户 ZIP/TAR 的解包接口。构建器拒绝指向包外的符号链接，安装器不允许用户选择一个新的预期哈希绕过校验。

## 验证口径

最新机器结果见 [managed-results.json](managed-results.json)，每项安装输出见 [安装证据](../../work-logs/evidence/m1-managed-install.json)，包大小与哈希见 [managed-artifact.json](managed-artifact.json)。

本次最终结果：23 项安装/隔离检查全部通过，53 项 Python 与 14 项 Node 测试通过。常规冻结程序和搬移后整程序禁网测试均通过 9 个有效样例、拒绝 13 个不应渲染的输入；标准 1 页、长样例 2 页。两份最终 PDF 的全部 3 页已用 Poppler 渲染目视检查，无缺字、截断、重叠或越界。

| 实测项 | 结果 / 口径 |
| --- | --- |
| 压缩包 | 57,502,535 字节，约 54.84 MiB |
| 包内普通文件总量 | 115,945,937 字节，约 110.57 MiB；不含文件系统分配与 `runtime.json` 自身 |
| 清单条目 | 234 个文件/内部符号链接；扫描 78 个 Mach-O 文件，无指向全局第三方目录的绝对动态依赖路径 |
| 本轮首次本地安装 | 18.55 秒，包含解包和校验；单次观察，不是冷启动基准 |
| 已安装版本复核 | 0.37 秒，单次观察 |
| HTTPS 中断后重试 | 8.91 秒，localhost TLS，不代表外网下载速度 |
| 整程序禁网自检 | 20.00 秒，包含全部 22 个输入及 PDF 检查；不是单份简历耗时 |
| 整程序 RSS 峰值采样 | 280,018,944 字节，约 267 MiB；非硬限制或保证峰值 |

本轮没有重新做 30 次发布包性能基准，不能直接沿用首轮全局 TeX 下的 P95 结论。两阶段编译现在显式调用 XeTeX 生成 XDV，再通过参数数组调用 xdvipdfmx，避免 XeTeX 内部 shell 对带空格安装路径的错误拼接；两阶段共享同一墙钟预算。

常规自检由冻结程序调用单独受限的 XeLaTeX 子进程。另一个测试将**整个冻结程序及其子进程**置于一层禁网沙箱内，搬移到含中文/空格的新目录后重新编译全部样例；同时验证包内文件可读、全局 TeX、全局 Python 和开发字体文件不可读。只允许必要 macOS 系统资源和当前包/作业目录，不靠删除现有工具模拟隔离。

macOS 拒绝在已受限进程内再次调用 `sandbox_apply`。因此外层固定样例测试使用专用的 `--outer-sandbox` 测试开关，依赖测试器施加的一层沙箱及进程组监控，不再嵌套第二层。该开关仅供固定虚构样例的测试器使用，不是生产编译 API；单独传它不代表已经施加沙箱。

HTTPS 测试使用临时生成的测试证书和 127.0.0.1 服务，实际传输运行时包，覆盖中断、重试和降级拒绝。证书只通过该次 curl 的 CA 参数环境生效，不安装进系统信任库。它验证真实 TLS/下载流程，不验证外部 CDN 可达性或广域网速度。

## 资源与已知限制

常规编译默认墙钟 30 秒、CPU 30 秒、单文件 64 MiB、FD 128；新增每轮约 50 ms 间隔的同进程组 RSS 采样，超过 512 MiB 就终止。采样本身也有耗时，短时峰值可能漏检或超出阈值；RSS 也可能重复计入共享页。**这是监控式保护，不是内核内存硬上限**。外层全程序测试统一监控进程组，阈值 1 GiB；其每个编译结果中 RSS 为 0/限制为 null，表示内层采样关闭，实际记录看顶层 supervisor。

尚未声明累计磁盘总量上限、可防止恶意进程脱离进程组，或支持任意 TeX。字体许可及主要 Python/native-library 原文随包保留，但静态链接库、格式文件的源码义务、完整 SBOM 与发布许可证仍需审核。Safari/Chrome 页面验收和真正冷启动也不由本轮结果替代。

开发基线调整：INS-01 按用户要求从当前工作清单跳过，不再作为本轮执行阻断；其他安全/许可与正式产品验收没有因此自动通过。M0 网页仍为模拟，未实施 M2。
