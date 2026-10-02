# M2 所有时间模块统一右对齐

## 改动

- 教育模块不再将日期接在学历详情后面：学校名称在左、日期同行靠右，下一行保留学历、专业和地点。
- 教育复用实习、项目、学术成果、竞赛与结构化自定义模块的标题渲染逻辑；学校行与详情行保留 2px 间隙，详情与正文保留 4px 间隙。
- 共用日期填充改为换行后仍保留的伸展空间，避免长标题将日期挤到下一行后又变成左对齐。只填日期、只填开始/结束月份也靠右，空日期不产生占位符。
- 不改数据契约、字号、页边距或保存内容；不缩小标题以硬塞进同一行。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -q
node --test tests/resume-library.test.cjs tests/avatar-model.test.mjs tests/markdown-model.test.mjs tests/section-model.test.mjs tests/style-model.test.mjs
.venv/bin/python -m scripts.check_date_alignment
.venv/bin/python -m scripts.check_entry_headings
.venv/bin/python -m scripts.check_fixed_spacing
.venv/bin/python scripts/check_backend.py
.venv/bin/python scripts/check_english_resume.py
```

- Python 138 项、Node 52 项通过。既有 Starlette/httpx 弃用提示保留，没有升级依赖。
- 新的日期实测覆盖六类模块、四种场景，共 28 个日期位置：普通标题、长中英文标题换行、仅日期、部分日期，同时使用不同页边距与字号。
- 从 PDF 文本运行矩阵读取实际起点，结合随附字体的字形前进宽度计算日期右边缘，误差最大为 0.0045 PDF bp；七个普通条目的名称与日期均在同一基线上。字体宽度使用原字体文件，避免 pypdf 对部分 CID 字体宽度的推断误差。
- 同行标题、正文间隔、固定留白、中英文真实 HTTP/TeX、备份与重启等已有回归继续通过。中文一页/两页基准页数未变。
- 虚构对齐测试 PDF 与当前英文 PDF 已经 Poppler 渲染目视检查；页面确认教育日期在学校行最右侧，未见文字截断、重叠或横向越界。机器证据见 `evidence/m2-date-alignment.json`。
- 8770 服务已重启加载新渲染器；重启前确认没有进行中的编译，仅对当前已保存的英文版本发起编译，预览/下载字节一致，仍为两页。全部已有简历文档的前后哈希一致，未覆盖用户最近的修改。
- 浏览器已展示更新后的教育模块，控制台无错误或警告。真实 PDF 和截图仅在忽略的 `output/pdf/private/` 与 `tmp/` 中保留，不提交个人资料。

## 边界

仅提交本地仓库，不推送远端。没有重新构建冻结运行时安装包，也没有恢复干净 Mac 或完整跨浏览器验收。
