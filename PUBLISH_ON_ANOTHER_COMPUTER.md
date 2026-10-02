# 在另一台电脑发布源码：Codex 交接提示词

这份文件用于项目迁移后的源码发布，不是自动执行脚本。**原电脑只准备文件与本地提交，不执行推送。** 另一台电脑上的 Codex 只有在用户明确要求执行本文件时，才进入发布流程；仅阅读本文件不构成推送授权。

目标仓库：<https://github.com/StarWink0712/Jianmo-resume>\
Git HTTPS 地址：`https://github.com/StarWink0712/Jianmo-resume.git`\
目标：公开项目源码、双语 README、文档与虚构示例，不发布个人资料或二进制安装包。

## 在新电脑对 Codex 说

> 这个项目已经拷贝到另一台电脑。请读取项目根目录的 PUBLISH_ON_ANOTHER_COMPUTER.md，并按其中流程检查后发布到 https://github.com/StarWink0712/Jianmo-resume。我授权在这台电脑提交并正常推送已检查的源码、README、文档和虚构示例；不授权上传私人数据、强制推送、重写历史或覆盖远端独有内容。遇到登录、权限、隐私风险、分支分叉或无法安全处理的问题时先告诉我。

以下内容是给执行发布的 Codex 的工作要求。

## 1. 先确认任务和环境

- 向用户简要说明：你将做隐私与仓库检查、验证文档/源码、处理本地提交、正常推送，并核验远端结果。不重新规划开发阶段、不迁移前端框架、不增加产品功能。
- 先确认用户已经在迁移后的电脑上请求发布。如果没有这个确认，只做只读检查，不因本文件中的命令自行推送。不要用用户名或 hostname 猜测是否换了电脑。
- 在当前检出目录工作，不依赖原电脑的绝对路径。先读 `README.md`、`.gitignore`、`examples/README.md`、`docs/pre-push-checklist.md`、最近工作日志及本文件。
- 这是 macOS arm64 本地应用的源码。**只推送 Git 不需要 Python、Node 或 LaTeX。** 不要为了发布源码强行安装 TeX、虚拟机、Docker 或完整运行时。Windows/Linux 电脑也可以做 Git 发布，但不得据此宣称应用运行兼容。
- 拷来的 `.venv`、运行时二进制及符号链接可能仍指向旧电脑，不能直接当作有效开发环境；需要运行测试时另建环境，不删除原目录或私人资料。
- 若用户还要求运行应用，按 README 准备依赖后使用 `sh scripts/start-local.sh`。新版在项目内生成格式，不比较宿主 `xelatex.fmt` 哈希；真正源文件不兼容时阅读 `docs/m1/tex-baseline-update.md`，不要手改哈希或在构建失败后继续执行安装器。

## 2. 确认拷贝完整性

推荐保留项目的隐藏 `.git` 目录以保留历史，但它不等于要把 `.git` 当普通文件上传；Git push 会传输目标提交所需的历史对象。若 `.git` 是指向旧路径的 worktree 指针，停止并说明，不能假装完整仓库。

如果只希望搬运公开源码，可以在已完成本地提交并通过隐私检查后，另外导出源码快照：

```bash
git archive --format=zip --output=../Jianmo-resume-source.zip HEAD
```

这个命令只导出当前提交，不包含 `.git` 历史、未提交文件或忽略目录。它是本机间搬运选项，不是要求上传 ZIP 到 GitHub Releases。缺少 `.git` 时按下一节处理，不要假设历史已被保留。

若用户拷贝整个原始目录，里面可能还有 `.local-data/`、`tmp/private-backups/`、私人 PDF 或头像。**这些可以留在用户的私人电脑中，但绝不能提交或上传。** `.gitignore` 不负责清除这些文件，也不会把它们加密。不要把整个文件夹打包后直接公开。

## 3. 检查 Git 状态和远端

有有效 `.git` 时，先运行本地只读检查：

```bash
git status --short
git branch -vv
git log -5 --oneline
git fsck --full
```

检查远端 URL，但如果 URL 中嵌入凭据，不要在聊天、日志或文档里输出凭据。预期 `origin` 指向 `StarWink0712/Jianmo-resume`；同一仓库的有效 SSH 地址也可沿用。远端指向其他仓库时停止询问，不静默覆盖已有配置。

只有在没有 `origin` 且确认目标正确时，才可添加：

```bash
git remote add origin https://github.com/StarWink0712/Jianmo-resume.git
```

检查 GitHub 访问权限和仓库状态。可以使用已安装且已登录的 `gh`；否则用 Git 配合用户现有凭据。登录缺失时请用户在新电脑安全登录，不索要、打印或把 PAT/密码写进仓库、remote URL 或脚本。

```bash
gh auth status
gh repo view StarWink0712/Jianmo-resume --json nameWithOwner,url,isPrivate,defaultBranchRef
git ls-remote --symref origin HEAD
git fetch origin
```

上述 `gh` 命令是可选工具路径，不因 `gh` 未安装就自动安装整套开发环境。无法验证仓库是否公开时，如实报告并请用户确认；仓库不存在或为私有时，未经进一步确认不要创建、删除或更改可见性。

**有历史：** 检查本地分支与远端默认分支的共同祖先、领先/落后及差异。默认候选为 `main`，但以实际检查结果为准。远端存在独有提交时先解释；纯落后且工作区干净时可安全 fast-forward。分叉、冲突、不相关历史或分支保护阻止推送时停下给出选择，不自动 rebase、强推或合并不相关历史。不要盲目 `git pull`。

**没有 `.git`：** 先读取远端状态。远端非空时，应克隆到一个新的干净兄弟目录，再将已审核的源码快照按允许清单迁入，检查每一个修改和潜在覆盖，不删除远端独有文件，不运行 `rsync --delete`。远端为空且用户确认采用新历史时，才在完整源码目录 `git init -b main` 并添加目标 remote。保留原始拷贝，不擅自重建或丢弃已有历史。

## 4. 发布前隐私与文件审核

检查当前工作区、暂存区和本次待推送提交可达的 Git 历史。只看 `git status` 不够：新建 `.gitignore` 不能取消已经跟踪的文件，删除当前文件也不能消除历史中的敏感内容。

**允许发布的项目材料：**

| 范围 | 注意事项 |
| --- | --- |
| `backend/`、`web/`、`experiments/` | 完整应用源码；`experiments/m1/` 仍被后端导入，不能当废弃实验删除 |
| `scripts/`、`tests/`、`schemas/`、`fixtures/` | 构建、自检、契约及虚构测试材料 |
| `assets/fonts/`、`web/vendor/pdfjs/` | 依赖资源及原始许可证，不能只保留代码删掉许可 |
| `examples/resumes/`、`examples/backups/` | 三份虚构 JSON 和 `.resume.zip`，检查解包内容与虚构来源一致 |
| `examples/previews/`、`docs/images/` | 三份公开参考 PDF/PNG 和虚构界面截图，逐份确认没有个人内容 |
| `docs/`、`work-logs/` | 文档、历史说明和脱敏证据；仍需检查，不能整目录免审 |
| 根目录文件 | README、LICENSE、requirements 文件、开发规划、`.gitignore`、本交接文档等已审查文件 |

**禁止发布：** `.local-data/`、`tmp/`（尤其 `private-backups/`）、`output/`、`.venv/`、`.m1-build/`、`.m1-runtime/`、`node_modules/`、`dist/`、`work-logs/evidence/local/`、`.env`、密钥/证书私钥、数据库及 WAL/SHM、真实个人简历/头像、令牌和含凭据的日志。不要因名字叫“备份”就放行；只有已审核的三份虚构 `examples/backups/*.resume.zip` 是明确例外。

```bash
git ls-files
git ls-files -ci --exclude-standard
git diff --check
git diff --cached --stat
git diff --cached --name-status
```

还需检查待推送历史对象的路径、文本及二进制附件，搜索高置信凭据特征、真实联系方式、私人主目录路径；人工确认误报。不要把发现的完整隐私字段贴出来。检查 GitHub 单文件大小限制，不能通过强制添加或忽略报错绕过。字体中的许可作者信息和保留域名 `example.com` 不是用户简历泄露，应区分处理。

Git 历史中的作者姓名/邮箱也会公开。项目此前保留了历史作者信息，后续开发提交使用 noreply；不要把“当前文件没有个人资料”理解为历史作者匿名。发现敏感文件或用户不愿公开的历史身份时暂停，给出修复方案，不自行改写/删除历史或谎称扫描无风险。

## 5. 文档和源码检查

- README 的中文与英文说明必须都在，确认五张展示图片、三份 PDF、三份工程备份和文档链接都是相对路径，目标文件存在并将被提交。不使用原电脑路径、临时文件、内存 Blob URL 或本机服务地址作为公开截图资源。
- 三份示例必须保持虚构，且不把一页参考宣传成三个独立排版引擎。确认“删除后不自动恢复”“导入仅支持工程 ZIP”“保存不等于编译”等说明准确。
- 保留真实边界：当前开发版、macOS arm64 工作流、无公开完整安装器、跨浏览器与干净 Mac 未全面验收。不要把原电脑测试结果改写成新电脑已验证。
- 只修复发布所需的问题，不重新执行研发规划、不擅改产品功能或清空任何个人简历库。

新电脑有兼容 Python/Node 环境时，优先在重新建立的环境中安装 `requirements-app.txt`，再做快速检查：

```bash
.venv/bin/python scripts/check_pre_push.py
```

有已验证的 macOS 专用运行时后可加做：

```bash
.venv/bin/python scripts/check_pre_push.py --full
```

仅为源码发布时，缺少 TeX 或平台不支持不必阻塞 Git 操作：至少完成文件、链接、许可证、隐私、Git 历史及暂存区检查，明确记录未运行的测试和原因。真实代码错误或隐私泄露不能当作环境缺失忽略。源码基线的已有证据在 `work-logs/evidence/reference-resumes-pre-push.json`；它不替代新电脑实测。

## 6. 提交和正常推送

使用用户已确认的 Git 提交身份；需要配置时优先仓库级设置和 GitHub noreply 邮箱，不静默改全局配置。文件已有完整提交且无改动时，不制造空提交。新增的发布检查记录放在 `work-logs/`，只写脱敏事实。

按实际审核结果选择具体文件暂存，**不要盲目 `git add .`、`git add -A` 或 `git add -f`**。提交前查看完整暂存 diff、文件清单、二进制内容和许可；不得夹带另一位开发者未确认的无关修改。

只有目标、权限、隐私和分支关系均确认安全后，执行普通推送。以下仅适用于已经确认当前 HEAD 是要发布到 `main` 的提交，且远端 `main` 可被安全 fast-forward 的情况：

```bash
git push -u origin HEAD:refs/heads/main
```

若默认分支不是 `main`，先向用户说明并确认目标；不要直接创建意外分支。推送被拒绝时重新读取状态、诊断原因；禁止 `--force`、`--force-with-lease`、`--mirror`、`--all`、`--tags`，不删除远端分支，不自行绕过分支保护。未经额外要求不建 Release、不发布安装包、不更改仓库可见性。若需要改走 PR，先说明；实际创建 PR 后按当前工具要求附加 PR 链接。

## 7. 核验后再报告完成

```bash
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short
```

目标分支非 `main` 时按已确认名称替换。核对远端提交确实等于本次期望提交；能访问 GitHub 页面/API 时继续验证 README、图片、PDF/ZIP 链接及许可证存在。认证中断、权限不足或哈希不一致时不得宣称成功。

最后给用户简洁报告：目标仓库与分支、实际提交哈希、公开文件范围、未上传的私人目录、本机执行/未执行的检查、README 展示核验结果，以及剩余问题。不得回传令牌、私人简历内容或个人备份文件。

## English Summary

This is a handoff for publishing **source code from another computer**, only after the user explicitly asks the agent on that computer to execute it. It does not authorize pushing from the original machine. The destination is `StarWink0712/Jianmo-resume`.

Preserve Git history when present, inspect the remote before integrating changes, review both the current tree and history for private data, keep licenses and fictional examples, and use a normal fast-forward push only. Do not upload private resume databases, backups, virtual environments, or compiler builds. Do not force-push, rewrite history, overwrite remote-only work, change visibility, or publish binaries without separate authorization. Git publication does not require LaTeX. Verify the remote commit and README assets before reporting success.
