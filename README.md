# 简墨 Jianmo Resume

**本地编辑，专业排版，让简历回归内容。**\
**Local editing. LaTeX typesetting. A resume that puts content first.**

浏览器填写与管理简历，本机保存、本机编译，免费导出无水印 PDF。支持中文、英文和混合内容，无需手写 LaTeX。\
Write and manage resumes in your browser, save and compile locally, and export watermark-free PDFs. Supports Chinese, English, and mixed-language content without writing LaTeX.

[中文说明](#中文) · [English Guide](#english) · [示例 / Examples](#examples) · [迁移与发布 / Publishing Handoff](PUBLISH_ON_ANOTHER_COMPUTER.md)

> **开发版 / Development Build**\
> 当前应用运行流程面向 macOS arm64，界面主要为中文。源码可公开阅读，但尚无完整、签名的开箱即用安装包。英文内容支持不等于已有英文界面或 Windows/Linux 运行支持。\
> The current application workflow targets macOS arm64 and the UI is primarily Chinese. This is source code, not a complete signed installer. English content support does not imply an English UI or Windows/Linux runtime support.

<a id="examples"></a>
## 示例 / Examples

### 我的简历 / Resume Library

按岗位保留不同版本；从旧简历创建独立副本，不覆盖原稿。下图为实际应用，卡片缩略图是内容示意，不是 PDF 截图。\
Keep separate versions for different roles. Duplicate a resume without overwriting the original. This is the actual application; card thumbnails are schematic, not PDF previews.

![三份虚构参考简历的管理页 / Library with three fictional reference resumes](docs/images/resume-library.jpg)

### 三份完整参考 / Three Complete References

三份均为 **一页 A4**，正文、模块和样式已填写。点击图片查看完整 PDF，下载工程备份后可在主页“导入工程”中导入。\
All three are **one-page A4** examples with populated sections and styles. Click a preview to open its PDF, or download a project backup and use **导入工程 (Import Project)** in the app.

| Java 后端 / Java Backend | 算法工程师 / Algorithm Engineer | 测试工程师 / QA Engineer |
| --- | --- | --- |
| [![Java 简历预览 / Java resume preview](examples/previews/java-developer.png)](examples/previews/java-developer.pdf) | [![算法简历预览 / Algorithm resume preview](examples/previews/algorithm-engineer.png)](examples/previews/algorithm-engineer.pdf) | [![测试简历预览 / QA resume preview](examples/previews/test-engineer.png)](examples/previews/test-engineer.pdf) |
| Java、Spring Boot、MySQL、Redis；订单系统与 RPC 项目。 | 推荐与检索、模型评估；研究报告与竞赛成果。 | 接口自动化、端到端回归、性能测试与质量保障。 |
| Spring Boot, databases, caching, order processing, and RPC. | Recommendation, retrieval, evaluation, research, and competitions. | API automation, end-to-end regression, performance, and quality. |
| [PDF](examples/previews/java-developer.pdf) · [工程备份 / Backup](examples/backups/java-developer.resume.zip) · [JSON](examples/resumes/java-developer.json) | [PDF](examples/previews/algorithm-engineer.pdf) · [工程备份 / Backup](examples/backups/algorithm-engineer.resume.zip) · [JSON](examples/resumes/algorithm-engineer.json) | [PDF](examples/previews/test-engineer.pdf) · [工程备份 / Backup](examples/backups/test-engineer.resume.zip) · [JSON](examples/resumes/test-engineer.json) |

**以上人物、单位、学校和经历全部虚构，没有使用用户的真实简历或照片。三份参考共用当前单栏排版模板，不是三个不同的排版引擎。**\
**All people, institutions, and experiences are fictional. No real user resumes or photos are included. These are three content references using the same single-column template, not three different layout engines.**

### 编辑与预览 / Editor and Preview

左侧填写条目标题、职责和日期，右侧查看真实 PDF。正文支持格式按钮，自动保存与 PDF 更新分开进行。\
Edit entry titles, roles, and dates on the left; inspect the actual PDF on the right. Formatting buttons assist with Markdown. Saving and PDF compilation are separate actions.

![Java 示例的编辑器与 PDF 预览 / Java example in the editor with PDF preview](docs/images/resume-editor.jpg)

<a id="中文"></a>
## 中文

### 能做什么

| 功能 | 当前行为 |
| --- | --- |
| 多份简历 | 新建、搜索、重命名、复制、删除；副本内容独立 |
| 本地保存 | 停止输入约 1 秒后自动保存到 SQLite；服务确认后显示已保存 |
| 真实 PDF | “保存并预览”调用专用 TeX；预览与导出的 PDF 字节一致 |
| 内容模块 | 基本信息、教育、实习/工作、项目、专业技能、获奖、学术、竞赛、自定义；支持排序与隐藏 |
| 正文格式 | 加粗、斜体、黑点/编号列表、显式换行、撤销/重做；编辑区保留 Markdown 标记 |
| 样式 | 六组共 36 种主题色、HEX 与原生调色盘；姓名/模块字号、整数页边距与模块间距；正文固定 1.35 倍行高 |
| 头像 | JPG/JPEG/PNG，原图不超过 1 MB；拖动、缩放、旋转，裁剪为 3:4 矩形 |
| 备份迁移 | 导出 `.resume.zip`，包含当前内容、样式和头像；导入创建独立副本 |
| 字体 | 随附 Noto Sans CJK SC 与 Noto Sans，界面和 PDF 使用项目字体，不依赖用户另装字体 |

主题色仅改变模块标题和分隔线，正文保持黑色。原生调色盘的吸管等能力取决于浏览器与操作系统。性别、年龄、头像等可不填；链接名称留空时直接显示网址。

### 本地启动

**需要什么：** 当前已验证环境为 macOS arm64；需要 Python 3.12+ 和项目专用 TeX 运行时。开发测试还需 Node.js。没有 npm 构建步骤，前端目前是原生 JavaScript，不是 React/TypeScript 工程。

```bash
git clone https://github.com/StarWink0712/Jianmo-resume.git
cd Jianmo-resume
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-app.txt
```

**首次克隆不会自带已构建的运行时。** 准备方式见 [专用运行时说明](docs/m1/managed-runtime.md)。当前构建器依赖匹配基线的本机 TeX Live、macOS arm64 和部分 Homebrew 构建环境；这不是任意 Mac 上装好 Python 就能一步运行的流程。哈希或依赖不匹配时应诊断原因，不要关闭校验。

具备上述构建条件的开发机可以执行：

```bash
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m experiments.m1.build_runtime
/bin/sh output/runtime/install-runtime.sh --prefix "$PWD/.m1-build/local-install"
.m1-build/local-install/current/resume-runtime verify
```

有兼容且已验证的专用运行时后，启动应用：

```bash
.venv/bin/python -m backend
```

打开 **http://127.0.0.1:8770/**，保持终端中的服务运行。用 `Ctrl+C` 正常退出。不要用 `file://` 或 `localhost` 替换该地址。端口可用 `--port 8775` 调整，浏览器地址也要相应改变。

安装好的专用运行时无需系统 LaTeX，但网页后端仍需上述 Python 环境。没有公开预构建下载包；完整应用尚未纳入冻结安装包。仅阅读文档、查看示例或通过 Git 推送源码，不需要安装 LaTeX。

### 从示例开始

1. 全新的数据目录会自动出现三份参考；已有简历库升级不自动添加。
2. 打开“Java 开发参考简历”，点击“创建副本”，命名为“Java 后端 · 校招版”。
3. 替换姓名、联系方式和真实经历，按岗位删减或调整模块。投递前删除虚构标记与“参考说明”，不要把示例经历当作自己的经历。
4. 输入结束后等待“已保存到本机”，点击“保存并预览”，检查页数，再“导出 PDF”。
5. 为另一个岗位创建第二份副本，比如“Java 后端 · 实习版”，原稿保持不变。

不需要参考时可以删除，刷新、重启、删空列表都不会自动恢复。主动想重新使用时，可在“新建简历”的“开始方式”选择参考，或导入仓库的工程备份。换成全新数据目录视为首次安装；希望首次即空库可用 `--no-examples`。

### 正文怎么写

下面是可放进正文框的写法示例。工具栏可生成相应标记，PDF 中只显示排版结果，不显示 `**` 等语法。

**Java 项目：职责与工程细节。**

```markdown
**技术栈：** Java、Spring Boot、MySQL、Redis。

- 通过唯一约束和状态机处理重复请求，覆盖超时取消与回调重试。
- 使用固定数据集对比索引调整前后的执行计划，并补充回归测试。
```

**算法项目：基线与可复现评估。**

```markdown
**研究方向：** 推荐与检索。

- 使用相同时间切分比较召回基线，记录 Recall@K 与分组指标。
- 保存随机种子和实验配置，报告多次实验波动，不把离线结果当作线上收益。
```

**测试项目：边界与证据。**

```markdown
**测试范围：** 下单、取消、支付回调。

1. 使用独立数据验证重复提交、缺失字段和越权访问。
2. 在失败报告中保留复现步骤与脱敏日志，避免记录令牌。
```

同一条目内写多篇论文时，输入第一篇后按 **Shift+Enter** 或点“换行”，再输入第二篇，不必加黑点。普通 Enter 是软换行；空一行表示新段落。示例引用应替换为真实成果：

```markdown
[1] **Example Author**. Retrieval Evaluation Notes. *Fictional course report*, 2026.

[2] **Example Author**. Reproducible Ranking Experiments. *Fictional project report*, 2026.
```

上面使用空行分段；要连续换行可改用工具栏“换行”。支持受限 Markdown，不接受原始 HTML、任意 TeX、代码块或正文图片；本 README 的代码围栏只用于展示输入示例。

### 数据与备份

| 文件/位置 | 用途 | 是否放进公开仓库 |
| --- | --- | --- |
| `.local-data/` | 私人简历、历史修订、头像、PDF | 否 |
| `tmp/`、`output/` | 临时文件、私人备份和构建/测试输出 | 否 |
| `examples/resumes/` | 三份虚构内容源 | 是 |
| `examples/backups/` | 可导入的虚构 `.resume.zip` | 是 |
| `examples/previews/`、`docs/images/` | 经检查的公开示例 PDF 与截图 | 是 |

主页“导入工程”只导入本项目的 `.resume.zip`，**不是导入任意 PDF、Word 或裸 JSON**。例如选择 `examples/backups/test-engineer.resume.zip` 后，会生成新的可编辑简历，不覆盖现有记录。工程备份不含历史修订、编译缓存或 PDF；PDF 供投递，不作为可编辑工程备份。

默认数据只在本机，应用没有云账号或云同步。数据目录不加密，同一操作系统用户的其他进程仍可能读取。迁移完整数据目录应先退出服务；日常跨机迁移建议逐份导出工程备份。`.gitignore` 只控制未跟踪文件，不能替代隐私检查。

<a id="english"></a>
## English

### Features

Jianmo is a local-first resume editor with a browser UI, a FastAPI/SQLite backend, and a dedicated TeX compiler. The current UI is primarily Chinese; English and mixed-language resume content are supported.

| Feature | Current behavior |
| --- | --- |
| Resume library | Create, search, rename, duplicate, and delete independently editable resumes |
| Local autosave | Saves roughly one second after typing stops; success means the server acknowledged the write |
| PDF output | **保存并预览 (Save & Preview)** compiles the saved content; preview and download use identical PDF bytes |
| Sections | Personal information, education, employment, projects, skills, awards, academic work, competitions, and custom sections; reorder or hide sections |
| Formatting | Bold, italic, bullet/numbered lists, explicit line breaks, undo/redo; the editor shows Markdown source |
| Styling | 36 preset colors in six groups, HEX and native color picker, font sizes, integer margins and section gaps; fixed 1.35 body line height |
| Photo | JPG/JPEG/PNG, original file up to 1 MB; pan, zoom, rotate, and crop to a 3:4 portrait |
| Portability | `.resume.zip` backups preserve current content, styles, and photo; import creates a new copy |
| Fonts | Bundled Noto Sans CJK SC and Noto Sans; no separate system font installation required |

Theme colors affect section headings and rules, not body text. Native color-picker features depend on the browser/OS. Gender, age, and photo are optional. Leave a personal link label blank to display its URL directly.

### Run Locally

**Prerequisites:** the currently verified workflow targets macOS arm64, Python 3.12+, and the project's dedicated TeX runtime. Node.js is needed for development tests. The frontend uses native JavaScript; there is no npm build step and no React/TypeScript migration to perform.

```bash
git clone https://github.com/StarWink0712/Jianmo-resume.git
cd Jianmo-resume
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-app.txt
```

**A fresh clone does not include a built runtime.** Follow the [dedicated runtime guide](docs/m1/managed-runtime.md). The current builder requires a matching TeX Live baseline, macOS arm64, and some Homebrew build dependencies. This is not a one-command installation on an arbitrary Mac. Do not bypass integrity checks if the baseline differs.

On a development Mac that satisfies those requirements:

```bash
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m experiments.m1.build_runtime
/bin/sh output/runtime/install-runtime.sh --prefix "$PWD/.m1-build/local-install"
.m1-build/local-install/current/resume-runtime verify
```

Once a compatible runtime is installed:

```bash
.venv/bin/python -m backend
```

Open **http://127.0.0.1:8770/** and keep the service running. Press `Ctrl+C` to exit normally. Do not substitute `file://` or `localhost`. Use `--port 8775` and the matching URL if needed.

The installed compiler runtime does not require system LaTeX, but the web backend still requires the Python environment above. There is no public prebuilt download or complete frozen application installer yet. Reading examples or pushing source code with Git does not require LaTeX.

### Try a Reference Resume

1. A brand-new data directory starts with the three [fictional references](#examples). Existing libraries are not changed on upgrade.
2. Open a reference, choose **创建副本 (Create Copy)**, and give the copy a role-specific name.
3. Replace personal information and experience with your own verifiable content. Remove fictional labels and the reference-note section before applying.
4. Wait for **已保存到本机 (Saved Locally)**, then click **保存并预览 (Save & Preview)**. Review page count and export with **导出 PDF (Export PDF)**.
5. Make another copy for a different application while keeping the original intact.

Delete unwanted references freely: refreshes, restarts, and an empty library do not restore them. To add one intentionally, choose it under **新建简历 (New Resume)** or import its bundled backup. A completely new data directory counts as a new installation; `--no-examples` opts out of first-use examples.

### Writing Examples

Put a title, role, and dates in their dedicated entry fields, then add details to the body. For example, **Order & Inventory Service / Backend Developer / 2025-03 to 2025-06** can use:

```markdown
**Stack:** Java, Spring Boot, MySQL, Redis.

- Handle duplicate requests with unique constraints and explicit state transitions.
- Compare query plans on a fixed dataset and add regression coverage.
```

An algorithm entry can describe evaluation rather than unsupported performance claims:

```markdown
**Focus:** Recommendation and retrieval.

- Compare recall baselines using the same time-based split and Recall@K metric.
- Record seeds, configurations, and variation across repeated experiments.
```

A QA entry can show test scope and reproducible evidence:

```markdown
1. Test missing fields, duplicate requests, and unauthorized access with isolated data.
2. Include reproduction steps and redacted logs in failure reports.
```

Use **Shift+Enter** or **换行 (Line Break)** for several publications within one entry without bullets. Plain Enter is a soft break; a blank line starts a new paragraph. Use **加粗 (Bold)** / `Cmd/Ctrl+B` and **斜体 (Italic)** / `Cmd/Ctrl+I`. Undo/redo history belongs to each body field and is reset on page refresh.

Only a restricted Markdown subset is supported. Raw HTML, arbitrary TeX, fenced code blocks, and inline images are not accepted as resume body content. Code fences in this README only illustrate what to type inside the body field.

### Backups and Privacy

**导入工程 (Import Project)** accepts this project's `.resume.zip` format, not arbitrary PDFs, Word files, or raw JSON. Try `examples/backups/test-engineer.resume.zip`: it creates an independent editable copy and does not overwrite an existing resume.

Backups include current content, styles, and photo, but not revision history, cached jobs, or PDFs. A PDF is a delivery document, not an editable project backup. Personal data lives in `.local-data/`; there is no cloud account or sync. The database is not encrypted, and other processes running as the same OS user may read it.

Do not publish `.local-data/`, `tmp/`, `output/`, virtual environments, or runtime build folders. Only reviewed fictional files in `examples/` and `docs/images/` are intended for public distribution. Stop the service before copying the whole data directory, or export individual backups for migration. `.gitignore` alone does not protect already-tracked files or history.

## 开发与验证 / Development and Verification

当前技术栈 / Current stack: native ES modules + CSS, FastAPI, SQLite, XeLaTeX/xdvipdfmx, and locally bundled PDF.js.

```bash
# Dependencies, contracts, Python/Node tests, and frontend syntax.
.venv/bin/python scripts/check_pre_push.py

# Also run ten real HTTP/TeX/PDF suites with an installed runtime.
.venv/bin/python scripts/check_pre_push.py --full

# Rebuild portable fictional backups and validate their lifecycle/PDFs.
.venv/bin/python -m scripts.build_reference_resumes
.venv/bin/python -m scripts.check_reference_resumes
```

测试在隔离目录运行，不操作个人简历库。完整测试使用端口 8771–8774、8782；日志位于 `tmp/pre-push/`。2026-10-02 的应用基线通过 152 项 Python、74 项 Node 测试和 25 个完整检查步骤；这是原开发机的记录，不是对任意环境的保证。\
Tests use isolated data, not the personal resume library. Full checks use ports 8771–8774 and 8782, with logs in `tmp/pre-push/`. The application baseline on 2026-10-02 passed 152 Python tests, 74 Node tests, and 25 full-check steps. These are recorded results from the development Mac, not guarantees for every environment.

证据 / Evidence: [完整回归 / Full checks](work-logs/evidence/reference-resumes-pre-push.json) · [参考简历 / Reference lifecycle](work-logs/evidence/reference-resumes.json) · [检查范围 / Validation scope](docs/pre-push-checklist.md).

### 项目目录 / Repository Map

| 路径 / Path | 说明 / Purpose |
| --- | --- |
| `web/` | 编辑器、管理页与本地 PDF.js / Editor, library, and local PDF.js |
| `backend/` | HTTP API、存储、备份与编译任务 / API, storage, backups, and jobs |
| `experiments/m1/` | 当前后端仍复用的渲染器、运行时与安全检查 / Renderer, runtime, and safety code still used by the backend |
| `schemas/`、`fixtures/` | 数据契约与虚构回归数据 / Contracts and fictional test data |
| `examples/` | 可编辑参考、备份、PDF 及预览 / Editable references, backups, PDFs, and previews |
| `scripts/`、`tests/` | 构建与验证入口 / Build tools and tests |
| `docs/`、`work-logs/` | 使用说明、技术记录与脱敏证据 / Guides, technical notes, and sanitized evidence |

### 边界 / Limitations

- 当前是 macOS arm64 开发流程，未承诺 Windows、Linux、Intel Mac 或任意 TeX Live 版本兼容。 / The current workflow targets macOS arm64, not Windows, Linux, Intel Macs, or arbitrary TeX Live versions.
- 应用只监听本机，不是多用户服务器，不应直接暴露到公网。 / This is a loopback-only, single-user application, not a public multi-user server.
- 已做内嵌浏览器与窄视口检查，独立 Safari/Chrome 全流程仍待验证；干净 Mac 验收未执行。 / Embedded-browser and narrow-viewport checks are recorded; independent Safari/Chrome and clean-Mac acceptance remain unverified.
- 内存采用 RSS 采样监控，不是内核硬上限；完整安装包的签名、公证和再分发审计尚未完成。 / Memory protection uses RSS sampling, not a kernel-enforced hard cap; signing, notarization, and full runtime redistribution review are incomplete.
- `docs/m0/editor-wireframe.html` 是历史模拟页面，不应作为当前应用入口。 / The M0 wireframe is a historical mockup, not the working application entry point.

### 更多文档 / More Documentation

[使用与存储 / Usage & Storage](docs/m2/README.md) · [API](docs/m2/api.md) · [字体 / Fonts](docs/m2/fonts.md) · [样式 / Styling](docs/m2/style-settings.md) · [正文格式 / Formatting](docs/m2/markdown-toolbar.md) · [参考维护 / Example Maintenance](examples/README.md) · [工作日志 / Work Logs](work-logs/README.md)

历史设计记录 / Historical design records: [开发规划 / Development Plan](resume-editor-development-plan.md) · [数据契约 / Data Contract](docs/m0/data-contract.md) · [技术决策 / Decisions](docs/m0/decisions.md).

贡献前请保持已有数据格式兼容，使用虚构测试材料，并说明实测环境与未覆盖范围。跨机发布源码的交接指令见 [PUBLISH_ON_ANOTHER_COMPUTER.md](PUBLISH_ON_ANOTHER_COMPUTER.md)。\
Contributions should preserve data compatibility, use fictional fixtures, and document tested environments and remaining gaps. For source publication from another computer, see the [publishing handoff](PUBLISH_ON_ANOTHER_COMPUTER.md).

## 许可证 / License

项目代码与虚构参考内容采用 [MIT License](LICENSE)。随附字体遵循各自 OFL 许可，PDF.js 遵循 Apache-2.0；原始许可证均保留。项目 MIT 不替代第三方编译运行时的全部再分发义务。\
Project code and fictional reference content use the [MIT License](LICENSE). Bundled fonts retain their OFL licenses; PDF.js retains Apache-2.0. The project license does not replace the redistribution obligations of the complete third-party compiler runtime.

[字体许可 / Font Licenses](assets/fonts/README.md) · [PDF.js License](web/vendor/pdfjs/README.md) · [运行时许可记录 / Runtime License Notes](docs/m1/licenses.md)
