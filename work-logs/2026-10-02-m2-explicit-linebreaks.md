# M2 正文显式换行

## 目的与改动

- 所有条目的正文工具栏新增“换行”按钮，支持 Shift+Enter，在同一条目内另起一行，不添加黑点或编号。
- 使用 CommonMark 的行末两个空格加换行作为存储形式，后端新增 `hardbreak` 白名单节点，生成受控的 `\newline{}`。手写反斜杠换行也兼容，不启用原始 HTML 或 LaTeX。
- 光标位于已有软换行两侧时升级为明确换行，避免多插入空段落；有选区时在选区后插入，保留选中的文字。复用已有硬换行时仍将光标移到下一行。
- 普通 Enter 的段内软换行和空行分段规则保持不变，不批量改写用户已有正文。换行采用已有固定正文行高。
- 复用正文历史、自动保存、长度限制与输入法组字保护。按钮、提示、使用说明及 Markdown 契约同步更新。

## 验证

```bash
node --test tests/resume-library.test.cjs tests/avatar-model.test.mjs tests/markdown-model.test.mjs tests/section-model.test.mjs tests/style-model.test.mjs
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m scripts.check_markdown_toolbar
```

- Python 136 项、Node 52 项通过。新增覆盖光标/选区、相邻换行、空白行、Unicode、撤销重做、显式/软换行差异、强调/链接/列表内换行、原始 HTML/TeX 仍被拒绝或转义，以及保存/备份保留两个尾随空格。
- 真实前端转换函数生成 Markdown 并通过 TeX 编译；同一条目中的 `[1]`、`[2]`、`[3]` 位于不同输出行，未变成列表，也未把方括号解释成 TeX 换行高度。既有黑点、编号、字体及强调断言继续通过，论文链接保留。
- `output/pdf/markdown-toolbar.pdf` 为可重建的虚构测试产物，已渲染整页目视检查，无重叠、截断或额外列表符号；机器证据见 `evidence/m2-markdown-toolbar-pdf.json`。
- 在 8774 隔离数据库中实测按钮、Shift+Enter、撤销/重做、自动保存、网页编译与刷新恢复。9999 字符继续插入换行时被正确拒绝，原文保留，撤销可恢复原测试正文。
- 默认桌面与 390px 窄屏无横向溢出，换行按钮可用；已恢复默认视口。浏览器控制台无错误或警告。截图放在忽略的 `tmp/m2/`，不包含真实简历内容。
- 8770 服务已重启加载渲染器，重启前确认无进行中的编译；所有已有简历文档的前后哈希一致。未合并、覆盖或调整用户的论文条目。

## 边界

只提交本地仓库，不推送远端。未重新打包冻结运行时，未新增通用富文本编辑器；不将本次内嵌浏览器结果当作独立 Safari/Chrome 或真实输入法全面验收。保留 Starlette/httpx 测试客户端的已知弃用提示。
