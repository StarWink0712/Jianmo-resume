# Windows / macOS 改造第一批：共享层与 macOS 执行器

日期：2026-10-02（Asia/Shanghai）。依据：`docs/windows-macos-platform-plan.md`。
代码起点：`3fa5ec0`；改造分支：`codex/windows-macos-platform`。

## 范围与保护

- 先完成 A 的回退准备，再实施 B/C 的共享逻辑和 macOS 平台边界。不改前端功能、工程格式或默认简历数据位置。
- `main` 保留在 `3fa5ec0`；规划单独提交为 `ba32c55`，代码与验证通过追加提交保存，不改写历史、不推送远程。
- 本地忽略目录 `tmp/platform-migration-backup-3fa5ec0/` 保存 Git bundle、迁移前检查结果和 SQLite backup API 生成的一致性快照。没有复制运行中的数据库主文件来冒充有效备份，也没有迁移或清空 `.local-data`。
- 改造前的源基线与通过证据按平台、资源摘要和实现摘要完整归档。原规划保持不变，本文件记录实际进度。

## 实现

- `core/resume_checks.py`：文字归一化、预期文字、样例和性能判定；`core/tex_checks.py`：PDF 与样例自检。后端及安装器不再导入完整实验脚本或冻结程序入口。
- `core/tex_pipeline.py`：共享格式生成和 XeTeX → XDV → PDF 流程。显式选择引擎/驱动，两个编译阶段共用剩余墙钟预算。主题、配置、清单和证据显式按 UTF-8 读取。
- `platform_adapters/macos.py`：数据/安装目录锁、私有权限、loopback 监听配置、最小环境、字体软链接、Seatbelt 沙箱与进程组监督。
- `platform_adapters/macos_exec.py`：独立子进程内设置 CPU、文件大小、文件描述符上限；正式路径完全移除 `preexec_fn`。返回结果区分启动失败、普通退出错误、墙钟超时、内存阈值和可识别的 CPU/文件限制信号，并记录清理动作。
- `platform_adapters/detect.py` / `contracts.py`：延迟导入、平台键及实际能力声明；`windows.py` 仅为明确拒绝执行的安全边界，不是原生 Windows 实现，不会用 chmod、裸进程或系统 TeX 降级运行。
- 编译缓存指纹覆盖平台、运行时清单、共享层、执行器与模板。安装版本身份也绑定完整实现摘要，避免代码变化却继续将旧安装当作本轮自检结果。
- `implementation_hash` 扩展到新目录与安装/后端实现，路径统一 POSIX 表示；证据绑定平台，禁止跨平台复用通过标记。历史目录使用源清单/实现摘要的组合哈希，最长仓库相对路径从 190 缩短到 125 字符，未改变任何历史证据内容。
- `scripts/check_platform_imports.py` 在独立进程禁止 macOS API 和实验运行器导入，并模拟非 UTF-8 默认编码；已纳入 pre-push 检查。旧实验入口保留兼容导出。

## 验证

已完成：

- 迁移前 pre-push 检查通过，结果在本地快照目录保留。
- 最终源码 Python 测试 196 项通过，较原来增加 21 项，包含 20 项平台契约测试及跨平台证据拒绝测试。
- 12 个正式/共享模块通过非 UTF-8、禁 Unix API 的独立导入检查。这是导入边界模拟，不是原生 Windows 测试。
- 最终 M1 候选：9 个有效样例、13 个预期拒绝、7 项隔离与 4 项超时/进程树探针通过；30 次两页编译 P50 0.936 秒、P95 1.046 秒。一页和两页样例逐页渲染检查无重叠、裁切、日期错位；归档路径调整后再次生成的两份 PDF 与已目视检查的前序候选逐字节相同。
- 新旧源资源清单摘要同为 `c439c4ee1102e48c36f5c11348301dd381b61bbcf1f190db98c8534117a84701`，新增/删除/变更均为 0；没有替换引擎锁或支持包，也没有批准跨机生成的格式缓存。

最终 UTF-8 修复及归档路径调整后的回归也已完成：

- `check_pre_push.py --full` 全部通过：196 项 Python、74 项 Node、12 个显式入口的导入检查、前端语法，以及 10 组真实 HTTP/PDF 应用检查。覆盖后端保存/备份、英文简历、各模块、样式、标题、间距、日期、Markdown、头像裁剪和参考简历。
- 精简运行时验证通过：格式生成失败保留旧安装；离线安装和重复安装；中文/空格路径搬移；22 项样例；隔离和超时探针；项目格式独占读取。安装结果 900 个清单文件、126,953,262 字节，不包含冻结 Python。
- 精简运行时两页完整后端编译采样 30 次，P50 2.064 秒、P95 2.126 秒，低于既有 3 秒门槛。该数据与开发源树的 M1 样本分开记录，不混用。
- 全新源码副本从空 `.venv`、空运行时启动，PATH 无全局 TeX/Homebrew，实际下载锁定引擎、重新生成格式并通过自检；HTTP 就绪，3 份参考简历均生成 1 页 PDF。
- 本项目的默认运行时已离线更新并通过自检，旧不可变版本目录保留；没有启动测试服务去操作 `.local-data`。
- 本地 Git bundle 校验成功，SQLite 快照 `PRAGMA integrity_check` 返回 `ok`。

最终证据：`docs/m1/baseline-evidence.json`、`docs/m1/results.json`、`work-logs/evidence/platform-macos-light-runtime.json`、`work-logs/evidence/platform-foundation-pre-push.json`。源基线与安装验收均绑定实现摘要 `ac46fed0da34b1b6f253f10383784266fdb0aa2fbda65cb630203e99c3ee9658`。三份历史归档的输入/结果哈希另行验证一致。所有测试仅使用虚构数据。

测试日志仍有既存的 Starlette/httpx 弃用提示，以及测试中的 SQLite ResourceWarning；未为消除提示升级依赖，也未将提示当作 Windows 兼容性证据。

主要复现命令：

```bash
.venv/bin/python scripts/check_platform_imports.py
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m experiments.m1.run --iterations 30 --report-dir output/platform-macos-final-candidate
.venv/bin/python -m experiments.m1.tex_baseline diff --candidate output/platform-macos-final-candidate
.venv/bin/python -m scripts.check_light_runtime --fresh-startup --report work-logs/evidence/platform-macos-light-runtime.json
.venv/bin/python scripts/check_pre_push.py --full
```

## 阶段与未完成项

| 规划步骤 | 当前状态 |
| --- | --- |
| A 固定现状 | 完成：分支、提交、历史/数据快照、旧证据保留 |
| B 共享逻辑 | 实现完成，macOS 与导入边界模拟已通过；真正的 Windows 导入验收仍待原生环境 |
| C macOS 适配 | 实现完成，最终源基线、精简安装、空环境启动与应用回归通过 |
| D Windows 最小原型 | 未完成：需真实 Windows 11 x64 普通用户环境 |
| E 统一安装入口 | 未实施：仍使用原 Mac 启动脚本、平台锁和 `current` 软链接，尚无 `bootstrap.py`、PowerShell 入口或 `current.json` |
| F/G 双平台验收与交付 | 未完成；README 只声明已支持的 macOS |

下一阶段先核验实际 Windows 上游 EXE/DLL 闭包，再验证 Job Object 的挂起启动/进程树清理、AppContainer 文件/网络隔离和私有 ACL；通过后才进入统一安装器。不能以 mock、WSL 或禁用沙箱替代这些门槛。

macOS 内存仍为 RSS 采样，文件限制仍为单文件 RLIMIT，不声称与 Windows Job Object 等价。本轮验证了正常退出、异常、超时及子孙清理，不保证宿主被强杀后的无条件清理。历史冻结运行时路线、Windows 原生浏览器、跨平台 `.resume.zip` 往返和干净实体 Mac 均未验收。
