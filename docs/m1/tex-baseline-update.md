# 可迁移 TeX 运行时与基线更新

## 普通使用：不修改哈希

当前支持 macOS Apple Silicon。安装 Homebrew 后，可准备依赖并启动源码：

```bash
brew install python openssl@3 zstd mpdecimal
brew install --cask mactex-no-gui
git clone https://github.com/StarWink0712/Jianmo-resume.git
cd Jianmo-resume
sh scripts/start-local.sh
```

已有 Python 3.12+、兼容 TeX Live 2026 和 Homebrew 构建依赖时，只需最后三个命令。MacTeX 下载较大，不是一个小型安装包。安装后的常规启动仍为 `sh scripts/start-local.sh`；可附加 `--port 8775`，然后打开对应的 `http://127.0.0.1:8775/`。第一次使用需联网安装 Python 依赖，此脚本不是无网络安装器。

脚本自动创建本项目的 `.venv`、安装依赖、构建并安装缺失/基线过旧的运行时、执行完整性检查并启动后端。任何步骤失败立即退出，不继续执行不存在的安装器。它不修改原有简历库，也不会删除已有运行时版本。不要从其他机器直接拷贝 `.venv`；可以通过 `PYTHON=/path/to/python3 sh scripts/start-local.sh` 指定兼容解释器。

`kpsewhich` 自动发现 TeX 根目录，`brew --prefix` 发现构建依赖；没有固定原开发机的 TeX 年份目录或 Homebrew 安装前缀。`/Library/TeX/texbin` 仅作为 MacTeX 注册入口的 PATH 后备，不是某台机器的 TeX 根目录。

## 为什么不再校验宿主格式文件

`xelatex.fmt` 是由 TeX 源文件预编译生成的格式缓存。不同机器可能拥有不同的生成时间、环境或内容；**仅看到 SHA-256 不同，不能判断其差异无害，也不能据此修改单个哈希**。

新的默认流程不读取宿主 `texmf-var/.../xelatex.fmt`，而是在项目私有目录内使用明确的 `xelatex.ini` 配方、固定环境和禁网沙箱重新生成格式。系统已有格式文件缺失、不同或损坏不会成为构建输入，也不会被修改。

安全校验分为两层：

1. **源输入基线**：严格校验实际使用的引擎、宏包、字体、CMap、许可文件及生成格式所需的源文件。原机定制的根目录 `texmf.cnf` 由项目受控配置替代；上游默认配置仍有校验。未批准的真实源码变化继续拒绝，不能用“兼容性”名义跳过。
2. **生成物完整性**：本次生成的 `formats/xelatex.fmt` 记录自己的哈希，并纳入安装包完整清单；冻结运行时真实 PDF 自检通过后才输出新的安装包和安装脚本。安装时继续校验包大小、SHA-256、文件清单和权限。

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
.venv/bin/python -m experiments.m1.build_runtime
.venv/bin/python -m experiments.m1.validate_managed
/bin/sh output/runtime/install-runtime.sh --prefix "$PWD/.m1-build/local-install"
.m1-build/local-install/current/resume-runtime verify
.venv/bin/python scripts/check_pre_push.py --full
```

按顺序执行且每一步成功后再继续。安装回归覆盖正常安装、重复安装、损坏/中断恢复、搬移到含空格和中文路径、冻结程序整进程禁网、全局 TeX/Python/开发字体不可读、网络正反对照及动态依赖路径。完整应用回归再验证真实保存/编译、样式、英文、头像与三份参考简历。

以上通过后，把代码、当前基线、审核说明和脱敏测试结果一起提交；不要提交 `output/`、`.m1-build/`、私人备份或用户数据库。如果实际测试失败，就修复或撤销未发布候选，不应仅把结果字段改成通过。

## 尚未提供的承诺

本项目目前没有可验证的公开预构建运行时下载地址。不要编造 GitHub Release URL、放宽下载哈希或宣称已经签名/公证。若未来公开预构建包，应固定版本及大小/SHA-256，完成第三方再分发审核，并由实际下载机器验证安装和离线使用。

RSS 保护仍为采样式监控，不是硬内存上限。当前源码启动脚本仅支持 macOS arm64；Windows/Linux 及 Intel Mac 需要另行实现和验证。此处不把原开发机的测试冒充用户新电脑验收。

## English Summary

On Apple Silicon macOS with Homebrew, install Python and the documented build libraries, install a compatible TeX Live 2026 distribution, clone the repository, and run `sh scripts/start-local.sh`. It creates the environment, builds/installs the required runtime, verifies it, and starts the backend, stopping immediately on failure.

The build discovers paths instead of using the original developer's directories. A host-generated `xelatex.fmt` is no longer an input: the project generates its own format from reviewed, hash-pinned TeX sources in a restricted environment. The resulting format is hashed as part of this build and the packaged runtime must pass real PDF self-tests. Actual upstream source changes still require the complete candidate, review, approval, package, and application validation workflow described above.
