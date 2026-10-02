# 学术、竞赛成果与自定义模块

在编辑器点击“模块管理”，选择“学术成果”“竞赛成果”或“自定义”，然后点击“新增模块”。
新增后自动选中对应页签，关闭模块管理即可填写；模块较多或屏幕较窄时，选中页签自动滚入视野。

## 条目字段

三种模块都支持多条记录，每条包含：

- 条目标题：论文/研究成果、竞赛名称或自定义事项，最多 200 字符。
- 个人角色：例如第一作者、共同作者、队长、独立开发，选填，最多 200 字符。
- 开始月份、结束月份：沿用项目/实习的 `YYYY-MM`；均可不填。勾选“至今”会清空并禁用结束月份，取消勾选后可重新填写。
- 可选链接：仅接受安全的 HTTP/HTTPS URL，不自动访问或抓取。PDF 显示“成果链接”或“相关链接”。
- 正文：沿用加粗、斜体、黑点/编号列表、撤销和重做工具栏。

条目标题加粗、个人角色同排，时间右对齐；标题下留 4 px 间距。长内容自然换行，不截断。
模块标题仍可改名，模块/条目支持排序、隐藏和删除。空字段不生成占位文本。
格式及内容按原规则自动保存；点击“保存并预览”更新 PDF。

## 数据兼容

新增类型为 `academic` 和 `competition`；与 `custom` 共用 `heading`、`role`、`start_date`、`end_date`、`ongoing`、`url` 和 `body`。
当前开发版 `schema_version` 仍为 1。新类型要求键齐全，空日期/链接为 null；旧自定义条目的新键可以缺省。
旧自定义内容打开后可见新表单，但不会仅因打开而补字段、增加修订或改写正文；实际编辑新增字段后采用同行标题布局。
旧自定义中的获奖经历继续保持直接正文模式；给这类旧模块增加条目时转换为正式 `awards` 类型，避免意外恢复旧隐藏标题。
新结构自定义模块即使改名为“获奖经历”，也保留标题/角色/时间，不再套用旧标题识别规则。

复制和备份保留全部字段、顺序及显隐；复制/导入生成新 ID，源简历不变。旧版程序可能拒绝新类型或新增字段，不声明能向旧版反向导入。
没有数据库表结构迁移；JSON 字段与渲染器的兼容规则由应用处理。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests
node --test tests/section-model.test.mjs tests/style-model.test.mjs tests/markdown-model.test.mjs tests/resume-library.test.cjs
.venv/bin/python -m scripts.check_achievement_modules
.venv/bin/python scripts/check_backend.py --port 8773
```

虚构输入见 `fixtures/achievement-sections.json`，真实 HTTP/PDF 证据见 `work-logs/evidence/m2-achievement-modules.json`。
覆盖同行标题、可选链接、隐藏记录、旧自定义、日期/URL/长度拒绝、重启、独立副本、全新数据库导入以及真实编译。
内嵌浏览器验证所有新模块的新增/录入、至今开关、格式工具栏和刷新持久化；默认桌面与 390×844 窄屏无横向溢出。不是 Safari/Chrome 全兼容验收。
