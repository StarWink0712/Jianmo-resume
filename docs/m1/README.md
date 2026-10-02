# M1 首轮技术验证

日期：2026-10-01。本文保留首轮开发机基准，后续已增加 [专用运行时与安装验证](managed-runtime.md)。M1 尚未签署完整验收，未进入 M2；干净 macOS 验收已按用户要求跳过，不记为通过。

本目录记录真实编译实验，不是安装完成声明。M0 页面仍使用模拟保存/编译，没有接入这里的 Python 代码，不持久化简历。

## 已实现的实验链路

`M0 JSON + 附件 -> 契约检查 -> Markdown AST 白名单 -> 单次 TeX 转义 -> 可信模板 -> 受限 XeLaTeX 子进程 -> Unicode 映射补齐 -> PDF 语义检查`

- 支持段落、加粗、斜体、安全链接和最多两层列表；不支持的 HTML、代码、图片、自动链接等明确拒绝。看起来像 TeX 命令的普通文字只作为文字输出。
- 固定字体文件，不依赖用户选择的系统字体。头像校验内容哈希、格式和尺寸后重新编码为 PNG。
- 独立作业目录、禁用 shell escape、受限环境变量、macOS 文件访问/禁网策略、墙钟超时和进程组清理。
- 另有 loopback HTTP 边界实验及下载哈希/大小/原子替换实验；不是生产 FastAPI 服务，也不是可用安装器。

实现入口：[实验主程序](../../experiments/m1/run.py)、[渲染器](../../experiments/m1/render.py)、[编译运行时](../../experiments/m1/runtime.py)、[HTTP/下载边界](../../experiments/m1/boundaries.py)。

## 复现

当前开发实验要求 macOS、可用的 `sandbox-exec`、Python 3.12+ 和已有 XeLaTeX/TeX Live；实际只验证了下表环境。TeX 中须包含 `fontspec`、`xeCJK`、`geometry`、`enumitem`、`needspace`、`graphicx`、`hyperref`、Fandol、TeX Gyre、Adobe CMap 及其依赖，`xelatex` 和 `kpsewhich` 须已可执行。这不是最终用户安装方式，也不要求为了本轮演示重新安装全量 TeX Live。

在项目根目录执行；已有 `.venv` 时复用，不修改全局工具：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-m1.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_contracts.py
node --test tests/resume-library.test.cjs
.venv/bin/python -m pip check
.venv/bin/python -m experiments.m1.run --iterations 30
```

`--iterations 1` 只用于冒烟检查，性能结论为未测试；正式性能记录至少 30 次。重复执行会更新本实验的报告与两份固定名称的 PDF，不应将手工文件存到这些路径。运行锁阻止两次完整实验共用作业目录；不要另起单独探针同时写同一目录。

生成位置：

- `output/pdf/m1-standard.pdf`：标准一页虚构简历。
- `output/pdf/m1-long.pdf`：两页长内容虚构简历。
- `docs/m1/results.json`：样例、文本、字体、页数、计时、安全探针及失败清单。
- `docs/m1/runtime-inputs.json`：字体/CMap 和 TeX recorder 实际输入的路径、大小、SHA-256。
- `.m1-runtime/`：从本机复制的字体、CMap、许可和环境清单，已忽略，**不是自包含运行时**。
- `tmp/pdfs/m1/`：可重建的作业目录、TeX 日志和检查图片，已忽略；只允许虚构数据。

使用已安装的 Poppler 复查排版，不需要联网：

```bash
pdftoppm -scale-to 1600 -png output/pdf/m1-standard.pdf tmp/pdfs/m1/standard-view
pdftoppm -scale-to 1600 -png output/pdf/m1-long.pdf tmp/pdfs/m1/long-view
```

## 本轮实测

| 项目 | 结果 |
| --- | --- |
| Mac | Apple M4 Pro，48 GiB 内存，arm64 |
| 系统 / 工具 | macOS 27.0，Python 3.14.7，Node 26.9.0 |
| 引擎 | XeTeX 3.141592653-2.6-0.999998，TeX Live 2026 |
| 渲染回归 | 9 个有效样例编译成功；11 个无效契约与 2 个不可渲染草稿按预期拒绝 |
| PDF | 标准 1 页、长样例 2 页；字体嵌入，中文提取通过；无 missing glyph / overfull hbox |
| 视觉检查 | Poppler 渲染全部 9 个有效样例，共 10 页；未见截断、重叠、越界或孤立模块标题 |
| 30 次两页样例 | P50 0.940891 秒，P95 1.007983 秒，最大 1.046318 秒；低于当前 3 秒目标 |
| 回归测试 | Python 42 项（M0 24 + M1 18）、Node 14 项通过；22 项契约样例无失败 |
| 字体 / CMap | 7 个字体共 19,081,960 字节；CMap 231,844 字节 |
| 实验资源目录 | `du -sh` 约 19 MiB，仍依赖已有引擎和宏包 |
| 已有完整 TeX Live | `du -sh` 约 9.7 GiB，不是计划分发包大小 |
| recorder 输入 | 标准样例记录 55 个 TeX 输入，7,407,132 字节；不是完整依赖闭包 |

计时口径：一次 XeLaTeX 编译 + Unicode 映射补齐 + PDF 结构/语义检查；每次新进程，复用已准备的本地依赖，系统缓存已热。P95 取排序后第 `ceil(30 * 0.95)` 项。**不含**下载、前端预览、JSON/Markdown 转换、首次依赖准备或真正冷启动；不能解释为用户端到端响应时间。下载量、独立运行时占用和真正冷编译尚未测量。

## 关键问题与限制

Fandol 的当前 XeLaTeX 输出缺少部分 `/ToUnicode`：仅检查编译成功或单一查看器会漏掉中文提取故障。实验只对已确认的 Adobe/GB1、Identity-H 字体补入标准 `Adobe-GB1-UCS2`，未知映射拒绝处理；补齐后再验证字体嵌入和期望文本。文本比较只折叠空白，不替换字符；这容忍了提取器对拉丁字距插入空格，但不意味着原始文本字节完全一致。

当前隔离使用系统 `sandbox-exec`，允许必要 OS 资源、已安装 TeX 根目录、固定字体和当前作业目录，只给祖先目录元数据权限。已经验证目录外测试秘密文件不可读、目录外不可写、禁网和禁用 shell escape；这些是定向探针，不是完整安全审计。设置 CPU 30 秒、单文件 64 MiB、FD 128 和默认墙钟 30 秒；只验证了墙钟与同进程组子进程清理，**没有验证内存硬限制、累计磁盘配额、逃离进程组的恶意子进程或所有资源耗尽场景**。不能把此实现作为任意 TeX 执行服务。

下载辅助函数仅验证固定大小/SHA-256、HTTPS 及返回 URL、失败清理和原子替换。测试使用注入下载流，不访问真实分发源；没有归档解包、签名、可达性、运行时安装、升级回退或完整重定向信任策略。

后续门槛与具体未测试项见 [验收矩阵](acceptance.md)；资源许可见 [许可清单](licenses.md)；执行过程见 [工作日志](../../work-logs/2026-10-01-m1-technical-validation.md)。
