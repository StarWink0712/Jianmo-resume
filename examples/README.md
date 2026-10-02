# 内置参考简历

这三份简历随源码一起分发，内容已填写，可直接编辑、创建副本或删除。它们是同一排版模板的不同岗位内容示例，不是三个独立排版引擎。

| 方向 | 内容重点 | 默认页数 | PDF 预览 | 工程备份 |
| --- | --- | --- | --- | --- |
| Java 开发 | Java / Spring Boot、数据库与缓存、订单系统、RPC 项目 | 1 | [Java PDF](previews/java-developer.pdf) | [Java 参考](backups/java-developer.resume.zip) |
| 算法工程师 | 推荐与检索、模型评估、研究报告、竞赛成果 | 1 | [算法 PDF](previews/algorithm-engineer.pdf) | [算法参考](backups/algorithm-engineer.resume.zip) |
| 测试工程师 | 测试设计、接口自动化、端到端与性能回归 | 1 | [测试 PDF](previews/test-engineer.pdf) | [测试参考](backups/test-engineer.resume.zip) |

所有人物、学校、单位、项目、研究与竞赛经历均为虚构。联系方式使用占位号码和保留域名 `example.com`，无真人头像，不含开发者或用户的个人简历。投递前请替换为真实信息与可核验经历，删除“参考说明”模块。示例内容与项目代码同样采用根目录的 MIT 许可证。

## 如何使用

1. 按根目录 README 准备依赖及专用 TeX 运行时，启动应用；全新的数据目录会自动拥有这三份参考简历。首次预览需点击“保存并预览”。
2. 在“我的简历”直接编辑，或点击“创建副本”保留原参考。
3. 不需要时删除。刷新、重启、删空简历库都不会自动恢复这些示例；已有用户升级时也不会被强行添加。
4. 以后主动需要时，可在“新建简历”的“开始方式”选择对应参考，或使用“导入工程”选择上表的 `.resume.zip`。导入生成独立副本，不覆盖现有简历。原始 JSON 不是主页导入格式。

自动初始化状态保存在数据目录的 SQLite 中，和三份示例在同一事务中完成；中途失败会回滚并在下次启动重试。删除数据目录或换成全新的目录视为首次安装，会重新提供示例。若希望首次启动就是空库，使用 `.venv/bin/python -m backend --no-examples`，之后正常重启仍保持空库。

## 内容维护与验证

`resumes/*.json` 是唯一内容源，采用项目 v1 简历契约。启动、新建及导入都会生成独立标识，不共享可变内容。备份包含 JSON 和校验清单，不包含历史记录、PDF 或私有数据。

修改 JSON 后重新生成可导入文件，并验证真实编译与持久化：

```bash
.venv/bin/python -m scripts.build_reference_resumes
.venv/bin/python -m scripts.check_reference_resumes
```

测试使用隔离目录和端口 8782，不访问个人数据库。验证首次初始化、真实 PDF 页数与完整文字、字体嵌入、编辑持久化、删除不复活、主动重建和独立新安装。生成的 PDF 位于忽略目录 `output/pdf/reference-resumes/`；报告为 `work-logs/evidence/reference-resumes.json`。

`previews/` 是从上述测试输出挑选、检查后公开的三份 PDF 和对应 PNG，用于 README 展示；不能把整个 `output/` 复制进来。内容调整后，应重新验证 PDF，再逐份替换公开文件。PNG 使用 Poppler `pdftoppm -scale-to 1400 -singlefile -png` 生成；若样例改成多页，需逐页渲染并相应更新 README，不得只保留第一页假装完整。

## English

These three fictional resumes ship with the source code and use the same single-column layout. The [bilingual main README](../README.md) includes screenshots, full-page previews, English instructions, and writing examples. Each reference currently fits on one A4 page.

- A brand-new data directory creates the three references once. Existing libraries are not changed on upgrade; deleted references do not return on refresh or restart.
- Edit a reference directly, duplicate it, or delete it. To recreate one intentionally, use the new-resume selector or import one of the `.resume.zip` files above. Raw JSON and PDF files are not project-import formats.
- People, institutions, experiences, and contact details are fictional. Replace them with verifiable information before applying. The examples use the project's MIT license; they contain no user photos or private resumes.
- `resumes/` is the content source; `backups/` contains importable archives; `previews/` contains reviewed public PDFs and rendered PNGs. Backups exclude PDFs, revision history, and cached jobs.
- After editing the JSON, run the build and validation commands above. Review the output and explicitly refresh only the three public PDFs/PNGs, not the entire ignored output directory.
