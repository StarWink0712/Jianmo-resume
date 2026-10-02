# 2026-10-01 / M1 / 首轮技术验证

时区：Asia/Shanghai。状态：首轮本机实验已完成，M1 整体尚未通过。

## 输入与范围

用户授权启动 M1。输入为 M0 范围、数据契约和虚构样例。本次验证结构化数据到真实中文 PDF、受限 Markdown、固定字体、离线/文件访问限制、进程超时、性能和安装校验策略。不接入 M0 页面，不实现 M2 数据持久化。

只使用虚构数据；不读取参考网站真实简历。不修改全局 TeX、Python、Node 配置。仅为本项目虚拟环境添加锁定的实验依赖。

## 初始环境

- 已安装 XeTeX / TeX Live 2026；系统发行版约 9.7 GiB（du 近似值），不能当作首版运行时预算。
- 可调用 macOS sandbox-exec；是否足够隔离仍需正反探针。
- 初选本机 TeX Live 内的 Fandol 中文字体、TeX Gyre Termes 拉丁字体，使用文件路径固定，不依赖用户系统字体选择。
- 当前不是干净 Mac；零预装安装验收不能由本机实验代替。

## 执行与证据

- 新增 `experiments/m1/`：契约/AST 渲染、固定字体模板、头像检查、隔离编译、Unicode 映射/PDF 检查、HTTP 和下载实验、计时与安全探针。
- 新增 `requirements-m1.txt` 并仅安装到项目虚拟环境；新增 18 项 M1 测试，不更改 M0 多简历行为。
- 保存 `docs/m1/results.json`、`runtime-inputs.json`、说明、许可和验收矩阵；更新项目与规划入口。
- 输出 `output/pdf/m1-standard.pdf`、`m1-long.pdf`，仅虚构信息；中间日志与图片存于已忽略的 `tmp/pdfs/m1/`。

主要执行命令：

```bash
.venv/bin/python -m pip install -r requirements-m1.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_contracts.py
node --test tests/resume-library.test.cjs
.venv/bin/python -m pip check
.venv/bin/python -m experiments.m1.run --iterations 30
pdftoppm -scale-to 1600 -png output/pdf/m1-standard.pdf tmp/pdfs/m1/standard-view
pdftoppm -scale-to 1600 -png output/pdf/m1-long.pdf tmp/pdfs/m1/long-view
```

最终结果：42 项 Python、14 项 Node 测试通过，22 项契约回归符合预期；真实编译 9 个有效样例，11 个无效契约和 2 个不可渲染草稿被拒绝。所有字体嵌入且有 Unicode 映射，期望文本无缺失，无 missing glyph/overfull hbox。目视检查 9 个有效样例共 10 页，含空白、头像、特殊字符、长字段、嵌套列表和显隐排序；无截断、重叠或越界。

最新 30 次两页热编译：P50 0.940891 秒、P95 1.007983 秒、最大 1.046318 秒。时间包括一次编译、Unicode 映射和 PDF 检查，不含真正冷启动或用户端到端耗时。当前文件/网络正反探针、禁用 shell escape、墙钟超时和进程组清理全部通过。证据摘要：[m1-checks.txt](evidence/m1-checks.txt)；完整测量：[results.json](../docs/m1/results.json)。

## 失败与修复记录

1. 初版 sandbox 阻止运行时祖先目录元数据查询，编译报 `lstat(/usr)` 失败。仅补充必要祖先的 metadata 访问，以及系统 shell 选择文件的只读访问；没有放开用户目录内容读取。
2. Fandol 在部分查看器中看似正常，但缺失 `/ToUnicode` 导致中文提取错误、Poppler 中文空白。补入已确认的 Adobe/GB1 CMap 并纳入资源哈希记录后，重新提取和渲染通过；不再以“能生成 PDF”作为唯一标准。
3. 初版章节分割线贴近标题。加入标题 strut 和正间距后重新生成/逐页检查，没有通过删内容或缩字号强行满足页数。
4. 网络正反探针起初都因 curl 的 SSL 配置读取被拒绝而失败，不能据此判定禁网有效。为两组探针加入同样的系统 SSL 配置只读权限，再验证允许组成功、拒绝组失败。此前失败未当成通过。
5. 单独探针与全量实验曾共用临时目录，导致诊断输出互相覆盖。加入完整实验的排他运行锁，停止并行写入后重新完成全量测试。
6. 复查实验断言，补充“应拒绝却被接受”、一页/两页目标和至少 30 次性能门槛；非 ASCII 请求令牌改为安全拒绝而非触发字符串比较异常。
7. `tlmgr --data revision` 不支持该字段，改用只读 `tlmgr info --only-installed` 取得实际 revision/许可元数据；没有更新系统 TeX。

## 决策与下一步

Fandol/TeX Gyre 仅为本轮候选，未锁定生产引擎或字体；本机 19 MiB 的复制目录不是独立引擎，完整 TeX Live 约 9.7 GiB 也不是计划分发体积。`.fls` 清单不是完整依赖闭包。

下一轮优先准备最小运行时和真实 bootstrap 安装，对照候选引擎、测冷启动与真实下载量，并安排干净 Mac 安装/断网编译。内存硬限制、最低 macOS、完整分发许可及 Safari/Chrome 尚待验证。详见 [M1 验收矩阵](../docs/m1/acceptance.md)。本轮不进入 M2，不接入生产保存/编译，不要求用户重配全局环境。
