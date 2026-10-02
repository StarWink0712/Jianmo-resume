# 虚构回归数据集

`resumes/standard.json` 是覆盖五类模块的完整虚构简历。姓名和机构均显式注明虚构，链接只使用保留的 `example.com`，电话留空。

`resumes/english.json` 是独立的全英文虚构回归样例，使用保留域名及虚构电话号码，覆盖长英文段落、引号/撇号、连续连字符、百分号、加粗/斜体、论文链接与六类模块。通过 `.venv/bin/python scripts/check_english_resume.py` 在隔离数据库中进行 12px/14px 真实编译、备份、副本与重启验证。它不包含用户提供的真实英文简历内容。

`cases.json` 定义基线上的确定性变体，`patches` 用数组路径和 `set` 操作覆盖字段，避免维护大量重复 JSON。`scripts/check_contracts.py` 的 `build_case` 在内存中生成独立样例，不修改基线；命令行 `--show <case-id>` 可打印实际 JSON。

```bash
.venv/bin/python scripts/check_contracts.py
.venv/bin/python scripts/check_contracts.py --show nested-lists
.venv/bin/python scripts/check_contracts.py --backup-manifest avatar
```

## 覆盖范围

正向样例覆盖空白、标准一页目标、两页目标、混排和特殊字符、长字段/URL、选填缺失、两层列表、排序和显隐、头像。非法样例覆盖危险 URL、URL 凭据和超长输入、重复 ID、悬空附件、日期冲突、未知字段、旧/新未知版本及无效日历时间。

另外两个 Markdown 草稿样例允许保存，但要求未来编译准备阶段拒绝：原始 HTML/危险链接/图片，以及超过两层的列表。M0 只检查结构，绝不把它们的“结构通过”当成安全渲染通过。

头像由检查脚本在内存中生成固定的 64×64 单色 PNG，无人物或真实照片。`make_manifest` 用真实字节长度和 SHA-256 构造可重建的备份载荷；当前仅检查 manifest 与载荷映射，不执行 ZIP 解压、图片解码、数据库导入或 ID 重映射。

## 后续补充

- M1：固定真实引擎/字体后保存基准 PDF，确认一页/两页目标，验证字符语义、链接和列表；现阶段没有 PDF 基线。
- M2/M4：补充实际 ZIP 归档夹具及路径穿越、重复成员、符号链接、解压炸弹、事务失败和导入 ID 重映射测试。
- M4：从真实历史发布版本生成旧备份；当前版本 0 样例只测试明确拒绝，不测试迁移。
- M3/M5：完整浏览器端到端测试与分页人工检查。
