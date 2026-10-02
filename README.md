# 简墨 Jianmo Resume

简墨：本地编辑，专业排版，让简历回归内容。

A local-first Chinese resume editor with LaTeX typesetting and free PDF export.
本地优先的中文简历编辑器：浏览器填写，LaTeX 排版，免费导出 PDF。

当前阶段：M2 本地后端与集成页已实现。新页面使用 SQLite 真实保存，并通过专用 TeX 生成 PDF；支持多简历、副本、头像及工程备份恢复。当前仍是开发版，不是正式公开发行版。干净 macOS 安装验收已按用户要求跳过，不算通过。

## 启动真实编辑器

当前为 macOS 本地开发流程。首次克隆需 Python 3.12+，在项目根目录执行（已有 `.venv` 可跳过创建）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-app.txt
```

按 [M1 专用运行时说明](docs/m1/managed-runtime.md) 准备并安装运行时，再启动服务：

```bash
.venv/bin/python -m backend
```

打开 **http://127.0.0.1:8770/**。不要用 `file://` 打开新页面，也不要用 `localhost` 替换该地址（Host 检查按启动地址匹配）。按 `Ctrl+C` 退出服务。

Git 仓库不包含 `.venv`、已构建的运行时或个人简历数据。运行时构建依赖开发机的 TeX Live，安装好的专用运行时不依赖系统 LaTeX；当前没有公开的预构建下载包。M2 后端暂未装进 M1 冻结安装包，仍需项目 Python 环境。

停止输入约 1 秒自动保存；只有后端确认成功后才显示“已保存到本地”。点击“保存并预览”生成 PDF，预览与下载使用同一任务的相同文件。默认数据库和头像位于 `.local-data/`，不要删除这个目录；重要简历建议另外导出工程备份。

详见 [M2 使用与实现说明](docs/m2/README.md)、[接口](docs/m2/api.md)、[本机验证与限制](docs/m2/acceptance.md)。

编辑器现支持六组共 36 种主题色、HEX/调色盘，以及像素制字号、模块间距和页边距；正文行高固定为 1.35，其他条目留白采用统一固定值。技能与获奖可直接编辑正文。入口为“样式设置”，详见 [主题与版式](docs/m2/style-settings.md)。

界面与 PDF 现在共用随项目/运行时分发的 Noto Sans CJK SC 2.004，无需安装系统字体或联网下载字体。旧运行时需重新构建并安装；资源缺失会明确报错。方案与验证边界见 [统一字体](docs/m2/fonts.md)。

## 项目入口

- [完整开发与验收规划](resume-editor-development-plan.md)
- [M0 范围基线](docs/m0/scope.md)
- [数据与备份契约](docs/m0/data-contract.md)
- [页面流程与状态规则](docs/m0/interaction.md)
- [技术决策与 M1 交接](docs/m0/decisions.md)
- [M1 实验复现与实测报告](docs/m1/README.md)
- [M1 验收状态](docs/m1/acceptance.md)
- [专用运行时与本地安装](docs/m1/managed-runtime.md)
- [M2 真实后端与集成页](docs/m2/README.md)
- [回归数据集说明](fixtures/README.md)
- [工作日志](work-logs/README.md)

[M0 历史交互稿](docs/m0/editor-wireframe.html) 可离线打开，它的保存、编译和导出仍为模拟。原 8765 地址也仍指向历史交互稿；**实际使用请打开新的 8770 地址**。

交互稿现在从“我的简历”进入，支持多份演示简历的新建、复制、重命名、删除和切换。页面内保留独立草稿，但刷新或关闭即重置，尚未持久化。

## M0 契约检查

开发检查使用 Python 3.12+。本机实际验证版本及结果见工作日志；这不是最终用户的安装方式，也不是生产 Python 版本决策。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -p test_contracts.py -v
.venv/bin/python scripts/check_contracts.py
node --test tests/resume-library.test.cjs
```

JSON Schema 定义结构约束；Python 检查补充跨字段约束。二者只是可执行的 M0 契约，不是生产输入过滤器、Markdown 渲染器或安全隔离实现。

Node 内置测试检查多简历的深复制、版本选择、状态隔离、重命名/删除与异步任务归属，不需要安装 npm 依赖。

## M1 编译实验

首轮基准仍可用本机 TeX Live 复现；第二轮将 Python 执行程序、引擎、宏包和字体打包到专用运行时，不需要用户另装开发工具。构建只在项目虚拟环境添加依赖，不修改全局 TeX 配置。使用与验证入口见 [专用运行时说明](docs/m1/managed-runtime.md)。

首轮生成一页和两页基准 PDF，30 次热编译 P95 约 1.01 秒；这是首轮开发机口径，不是安装耗时。第二轮安装、搬移和隔离测试以 [最新报告](docs/m1/managed-results.json) 为准。M0 页面中的保存/编译仍然是模拟。

## 执行纪律

M0 的执行默认值取自现有规划，不代表用户逐项签字或产品兼容性已通过。范围调整要同步契约、样例、测试及工作日志。本轮按用户要求进入 M2 后端开发；M1 中未通过的再分发许可、硬资源限制、跨浏览器和发布验收要求仍保留，不能因端到端流程跑通而自动通过。

## 许可证

项目代码使用 [MIT License](LICENSE)。随附字体及 PDF.js 遵循各自许可证，见 [字体说明](assets/fonts/README.md) 和 [PDF.js 说明](web/vendor/pdfjs/README.md)。项目许可证不替代运行时第三方组件的再分发审计。
