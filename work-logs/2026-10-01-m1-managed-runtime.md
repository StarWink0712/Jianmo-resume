# 2026-10-01 / M1 / 专用运行时与本地安装验证

时区：Asia/Shanghai。状态：本轮专用运行时/安装器实现与本机验证完成；不是完整 M1/发布验收通过。

## 用户决定

本轮用户明确跳过真正干净 macOS 的安装验收。INS-01 记为“用户决定跳过”，不是通过，不再作为本轮工作阻断；不创建虚拟机，不卸载现有工具，不把隔离的开发机测试冒充干净 Mac。

## 执行范围

制作可搬移的固定模板编译运行时，包含 Python 执行程序、XeLaTeX、宏包、字体/CMap；实现用户权限本地安装器，测试安装、重复执行、损坏包、失败重试、禁网编译和全局依赖不可读。只使用虚构简历，不接入 M0 页面或实现 M2 后端。

构建可读取已有开发工具，安装后的执行必须不依赖它们；系统组件与用户安装的开发工具区别记录。完整再分发许可、签名/公证、最低系统兼容不能凭本机成功推断。

## 结果

- 新增可搬移的冻结 Python 执行程序、固定模板专用 TeX 目录、文件/权限/链接清单、自检 CLI 与内嵌哈希的 shell 安装器。
- 包含 Python、所需依赖、XeTeX、xdvipdfmx、宏包、格式、字体/CMap；仅在构建时读取开发机工具，安装后已验证不读取全局 Python/TeX/开发字体。
- 安装支持用户目录、本地归档、HTTPS、先校验后解包、原子切换 current、重复安装验证、并发锁和失败清理；不修改 PATH/profile/全局配置。
- 增加同进程组 RSS 监控与超限终止/恢复测试，明确不是硬内存上限。
- 23 项真实安装/隔离检查全部通过；53 项 Python、14 项 Node 测试通过，22 项契约样例符合预期，pip check 与 Python 编译检查通过。
- 常规自检和整程序禁网自检均编译 9 个有效样例并拒绝 13 个不应渲染输入。基准仍为一页/两页，字体嵌入、Unicode 映射和期望文本检查通过；最终交付的 3 页 PDF 已目视检查，无缺字、重叠、截断或越界。
- 本地包 57,502,535 字节，包内普通文件 115,945,937 字节，234 项清单条目；78 个 Mach-O 文件没有全局第三方绝对动态链接路径。此静态检查不替代完整依赖/许可审计。
- 本次首次本地安装 18.55 秒、已安装复核 0.37 秒、localhost HTTPS 重试安装 8.91 秒；仅单次观测。整程序禁网样例自检 20.00 秒，RSS 峰值采样约 267 MiB；不能当作单份编译性能或硬上限。

最终安装器还执行到项目的 `.m1-build/local-install` 并验证成功，可直接运行其中 `current/resume-runtime`。不安装到用户全局应用目录。产物与中间文件已忽略，未作 Git 提交。

## 复现命令与证据

```bash
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m experiments.m1.build_runtime
.venv/bin/python -m experiments.m1.validate_managed
.venv/bin/python -m unittest discover -s tests -v
node --test tests/resume-library.test.cjs
.venv/bin/python scripts/check_contracts.py
.venv/bin/python -m pip check
/bin/sh output/runtime/install-runtime.sh --prefix .m1-build/local-install
.m1-build/local-install/current/resume-runtime verify
```

[说明与使用](../docs/m1/managed-runtime.md)、[机器结果](../docs/m1/managed-results.json)、[安装输出](evidence/m1-managed-install.json)、[单元回归](evidence/m1-managed-checks.txt)、[产物哈希](../docs/m1/managed-artifact.json)。本轮两份 PDF 位于 `output/pdf/m1-managed-standard.pdf` 与 `m1-managed-long.pdf`。不覆盖首轮 PDF/性能报告。

## 失败与修复

1. 仅复制首轮 `.fls` 文件不足：`article`/`fontspec` 初始化读取 Latin Modern Roman 10 及 tex-text 映射。补齐四个字形文件和映射，保留许可证后，在禁用全局依赖条件下通过。
2. 初版解包受安装器 umask 影响，权限清单不一致。对已通过完整哈希校验的受信任归档使用保留权限解包，仍在切换版本前验证；失败阶段没有覆盖旧版本。
3. macOS 不允许已沙箱进程再次 sandbox_apply，也禁止其中运行带特殊权限的 ps。整程序固定样例测试改为一层外部沙箱/监控覆盖父子进程；常规模式保持逐编译子进程隔离。不放开全局依赖或网络来掩盖错误。
4. 带空格的安装目录导致 XeTeX 的内部 PDF 驱动 shell 命令失败；显式指定相对 output-driver 也未解决。改为 XeTeX `-no-pdf` 生成 XDV，再以参数数组直接启动包内 xdvipdfmx，两阶段共享墙钟预算。中文/空格路径及搬移回归随后通过。
5. stdout 中 JSON 转义后的中文路径未被最初的字符串脱敏捕获，补充普通/JSON 转义两种路径脱敏及单元测试，最终保存证据已移除个人绝对路径。

## 保留限制

干净 Mac 明确跳过；未测试公开 CDN、最低 macOS、Safari/Chrome，不承诺跨机器可用。发布包性能尚未重新跑 30 次，不能沿用首轮 1.01 秒 P95；未实现内存硬限制、累计磁盘配额、崩溃/断电安装自动恢复。许可原文随包保留，但完整静态依赖和再分发义务、项目发布许可证、Developer ID/公证仍待审核。页面保存/编译依然是模拟，本轮没有进入 M2。
