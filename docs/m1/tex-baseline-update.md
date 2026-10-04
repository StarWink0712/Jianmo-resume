# 可迁移 TeX 运行时与基线更新

## 普通使用：不修改哈希

当前支持 macOS Apple Silicon 和 Python 3.12+。普通用户不需要 MacTeX、TeX Live 或 PyInstaller。没有 Python 时可通过 Homebrew 安装，再启动源码：

```bash
brew install python
git clone https://github.com/StarWink0712/Jianmo-resume.git
cd Jianmo-resume
sh scripts/start-local.sh
```

已有 Python 3.12+ 时只需最后三个命令。首次安装 Python 依赖并下载约 16.2 MB 的两个 TeX 引擎包，必要宏包和字体已随源码提供；不会下载安装完整 TeX。常规启动仍为 `sh scripts/start-local.sh`，可附加 `--port 8775`。环境准备完毕后，可用 `.venv/bin/python -m backend` 离线启动。

脚本自动创建本项目的 `.venv`、安装依赖、安装精简运行时、执行完整性及真实 PDF 检查并启动后端。失败时立即停止，不切换到半成品；不修改简历库或删除旧运行时。不要跨机复制 `.venv`；可以用 `PYTHON=/path/to/python3 sh scripts/start-local.sh` 指定解释器。

运行时来源、校验、缓存及离线迁移见 [精简运行时](../../runtime/README.md)。只有维护者重建 TeX 资源时才需要本机 TeX；`kpsewhich` 自动发现其位置。普通启动不读取系统 TeX 路径、宏包或格式缓存。

## 为什么不再校验宿主格式文件

`xelatex.fmt` 是由 TeX 源文件预编译生成的格式缓存。不同机器可能拥有不同的生成时间、环境或内容；**仅看到 SHA-256 不同，不能判断其差异无害，也不能据此修改单个哈希**。

新的默认流程不读取宿主 `texmf-var/.../xelatex.fmt`，而是在项目私有目录内使用明确的 `xelatex.ini` 配方、固定环境和禁网沙箱重新生成格式。系统已有格式文件缺失、不同或损坏不会成为构建输入，也不会被修改。

安全校验分为两层：

1. **源输入基线**：严格校验实际使用的引擎、宏包、字体、CMap、许可文件及生成格式所需的源文件。原机定制的根目录 `texmf.cnf` 由项目受控配置替代；上游默认配置仍有校验。未批准的真实源码变化继续拒绝，不能用“兼容性”名义跳过。
2. **生成物完整性**：本次生成的 `formats/xelatex.fmt` 记录自己的哈希并纳入本地安装清单；只有真实 PDF 自检通过才切换当前版本。下载包大小/SHA-512、支持包 SHA-256、引擎和源文件哈希均独立校验。

这解决的是“同一支持的 TeX 源码，在不同电脑拥有不同格式缓存”的可迁移性。并不意味着任意 TeX Live 版本、任意新增宏包或其他操作系统都自动受支持。上游真实输入变化需要维护者按下面流程更新基线；普通用户不应反复审批自己的机器哈希。

## 维护者：完整更新流程

候选实验与已批准基线分开。实验失败、少于 30 次基准采样、证据过期或未完成人工依赖审阅，均不能成为默认构建基线。以下工作不会清空个人简历数据库。

### 1. 生成候选证据

```bash
.venv/bin/python -m experiments.m1.run --iterations 30 --report-dir output/m1-candidate
.venv/bin/python -m experiments.m1.tex_baseline diff --candidate output/m1-candidate
```

必须检查退出码。实验涵盖全部有效/非法输入、中文与混合文字、空内容、一页/两页目标、PDF 文字/字体/溢出、30 次性能样本、文件读写、shell escape、网络正反对照、超时及进程组恢复。候选依赖是所有有效用例的输入并集，并显式补充格式生成输入与打包资源，不再只记录一份简历。

候选目录保存 `runtime-inputs.json`、`results.json`、`baseline-evidence.json`、`dependency-diff.json`、`pdf/` 与 `work/`。证据绑定输入清单、实验结果及验证实现哈希；修改校验代码或候选清单后要重新运行，不可拼接旧的“通过”报告。

平台改造后的 `platform-v1` 摘要还覆盖 `core/`、`platform_adapters/`、后端与精简安装/构建代码，路径按 POSIX 表示序列化。证据记录 `platform_key`，不允许跨平台沿用通过记录。历史归档键为平台加源清单/实现摘要的组合哈希，避免两段长摘要嵌套占用 Windows 路径长度；完整摘要仍保存在归档证据中，相同资源但不同执行器的记录不会互相覆盖。

### 2. 审核变更

逐项审查新增、删除及哈希变化的输入，区分上游宏包/引擎升级、格式缓存移除、生成格式的新源文件、字体与许可变化。对照 `work/*/main.fls`、`.m1-runtime/format-build/xelatex.fls` 与 TeX 日志，说明来源和必要性。使用 PDF 查看器或 Poppler 逐页检查候选输出，不仅依赖文字提取。

在项目中创建一份审核 Markdown，写明平台/工具版本、差异类别、异常处理、PDF 目视结果及仍未验证的范围。保留旧基线，不修改单个输入哈希。`diff` 命令打印的是整个候选清单的哈希，不是允许忽略错误的开关。

### 3. 显式批准候选

用真实审核文件及上一步打印的完整 SHA-256 替换占位符：

```bash
.venv/bin/python -m experiments.m1.tex_baseline approve \
  --candidate output/m1-candidate \
  --review docs/m1/your-baseline-review.md \
  --expected-sha256 FULL_CANDIDATE_SHA256
```

程序复核全部候选证据，将旧基线保存在 `docs/m1/baseline-history/`，更新当前清单/结果并记录审核文件摘要。这是源码基线批准，不代表已通过二进制分发许可或新机器验收。

### 4. 构建、安装与回归

```bash
.venv/bin/python -m scripts.build_light_runtime
.venv/bin/python -m scripts.light_runtime
.venv/bin/python -m scripts.check_light_runtime --fresh-startup
.venv/bin/python scripts/check_pre_push.py --full
```

按顺序执行且每一步成功后再继续。安装回归覆盖正常安装、重复安装、失败恢复、搬移到含空格和中文路径、无全局 TeX 的全新源码启动，以及编译器隔离/超时。完整应用回归再验证真实保存/编译、样式、英文、头像与三份参考简历。若源清单完全未变，不必重建支持包。

`experiments.m1.build_runtime` 和 `validate_managed` 属于历史冻结运行时路线，不是当前普通启动的前置依赖。本轮平台拆分不验收该路线；重启二进制分发工作时需单独适配并重跑，不能复用历史包的通过记录。

以上通过后，把代码、当前基线、审核说明和脱敏测试结果一起提交；不要提交 `output/`、`.m1-build/`、私人备份或用户数据库。如果实际测试失败，就修复或撤销未发布候选，不应仅把结果字段改成通过。

## 尚未提供的承诺

普通安装直接从锁定的 TeX Live 包安装必要引擎，有经过验证的 HTTPS 镜像及带日期的历史快照后备，不依赖本项目 GitHub Release。不要把维护者的旧冻结运行时包当成公开发行版；对它另行分发仍需处理静态库源码及再分发义务，也不能宣称已有签名/公证。

RSS 保护仍为采样式监控，不是硬内存上限。`start-local.sh` 面向 macOS arm64；Windows 11 x64 使用 `scripts/bootstrap.py` 或 `start-local.ps1`，见 README。Linux 及 Intel Mac 尚未支持。此处不把原开发机的测试冒充用户新电脑验收。

## English Summary

On Apple Silicon macOS with Python 3.12+, clone the repository and run `sh scripts/start-local.sh`. Setup downloads only about 16.2 MB of hash-pinned upstream TeX engines, uses the included support files and fonts, generates a private format, verifies real PDFs, and starts the backend. No full TeX distribution or PyInstaller is needed. Only maintainers rebuilding the support archive need a compatible local TeX tree.

The build discovers paths instead of using the original developer's directories. A host-generated `xelatex.fmt` is no longer an input: the project generates its own format from reviewed, hash-pinned TeX sources in a restricted environment. The resulting format is hashed as part of this build and the packaged runtime must pass real PDF self-tests. Actual upstream source changes still require the complete candidate, review, approval, package, and application validation workflow described above.
