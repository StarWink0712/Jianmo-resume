# Windows 本机应用验收

2026-10-04（Asia/Shanghai）。用户要求继续开发直至 Windows 版本可以正确运行。本轮已接通实际应用，不再只运行独立编译原型。验收平台为本机 Windows 11 x64 10.0.26200、CPython 3.12.6 x64、默认 cp936，未提权。

## 当前可用范围

- PowerShell 薄入口 `scripts/start-local.ps1`，或直接用 Python 执行 `scripts/bootstrap.py`。共享启动器准备/复用本机虚拟环境、固定依赖与运行时，任一步失败都不启动后端。已有依赖和运行时支持 `--offline`，无需激活虚拟环境、管理员、开发者模式、WSL 或系统 TeX。
- Windows adapter 使用已验证的 AppContainer、Job Object 和实际 DLL 加载审计。没有有效运行时清单或没有隔离作用域时拒绝执行；仅允许固定 XeLaTeX 和 xdvipdfmx 入口。两个阶段共用剩余墙钟预算，内存仍记录 Windows Job commit，不能冒充 macOS RSS。
- 每次编译固定同一个不可变运行时目录，以独占原生租约协调跨服务访问，避免并发覆盖 AppContainer ACL。编译后清除该身份的运行时/作业访问权限。作业中的日志随任务清理，PDF 保存在 SQLite 中。
- 使用 `SO_EXCLUSIVEADDRUSE`，先占用 loopback 端口再打开数据目录。SQLite、已有 WAL/SHM 使用真实私有 DACL；打开前拒绝重解析点和硬链接。新旧数据不合并、不清空。工程迁移仍使用 `.resume.zip`。
- 运行时检查与编译入口通过 `core/managed_runtime.py` 分派，Windows 不调用 Mac 清单验证或 Mac 原生 API。Mac 执行路径保持原有实现；共享包装层的测试通过，但本分支仍需在 Mac 上做原生回归。

## 安装迁移问题与修复

在暂存目录中执行 EXE 后仅重命名目录，实测迁移后的调试事件会缺少可验证的映像文件句柄，审计因此拒绝执行。诊断对照中，同一组字节复制为新文件后可以正常审计和执行。安装事务现先验证暂存树，再复制成新文件身份、重新验证、移动尚未执行的副本，最后切换 `current.json`。没有绕过缺失句柄、路径或哈希检查。

全新安装与落定后重新编译分别跑过三份参考简历和全部 22 项固定样例：9 项正常 PDF、13 项预期拒绝。离线再次安装没有重新生成格式。落定后刻意占用首选别名盘符仍可编译，编译前后运行时内容清单保持相同。

当前安装身份：`8b068bf64e30d996a1fd5792b098716934a9f05da4377014d26852966277408e`。本次清单为 1,153 个文件、119,394,688 bytes，不含清单自身和临时作业。三个下载档案共 11,755,948 bytes。源码或构建输入改变后身份会变，启动器会重新安装验收，不手工改清单哈希。

## 实际验证

- 最终开发检查：145 项 Python 用例、74 项前端 Node 用例，无跳过；17 个生产/共享入口的非 UTF-8 默认编码导入通过；`pip check`、数据契约通过。
- 网络隔离：DNS、公网 IPv4 TCP、本机局域网地址、loopback 拒绝；宿主正向控制可用。IPv6、另一台局域网机器和独立的非管理员组账户尚未覆盖。
- 真实后端（没有 FakeCompiler）：保存姓名/配色，编译真实一页 PDF，预览与下载字节相同、文字含保存的姓名；工程导出内容完整，导入创建独立副本；Mac 样例工程导入内容/样式/顺序保留；服务重启后数据和 PDF 保留；任务目录清空。一次完整编译约 22.4 秒，仅为单次观测，不是性能保证。
- 已有测试在 Windows 暴露两处跨平台问题并修复：中文 JSON 测试显式指定 UTF-8；SQLite 测试显式关闭连接，不能把连接上下文的事务提交误当成关闭文件。
- 浏览器实际操作：打开简历、修改虚构姓名、点击保存并预览；页面显示“已保存到本机”“预览已更新 · 1 页”，PDF 文字与修改一致。内嵌浏览器的下载事件没有完成，页面无 console error；工程中原有提示建议用独立浏览器下载。
- 尝试独立 Chrome 下载验收时，电脑操作工具因无法可靠识别当前网址而停止。未绕过该限制，也没有把浏览器文件落盘标记为通过。PDF 下载接口字节检查已通过。
- 另对测试服务实际 TCP 端口执行带会话鉴权的下载并落盘：HTTP 200、`application/pdf`、附件响应头正确，90,840 bytes 与预览完全一致，PDF 一页且含浏览器保存的虚构姓名。此项是 HTTP 下载验收，不代替独立浏览器下载交互验收。实际页面截图保存为 `evidence/windows-2026-10-04-browser.jpg`。
- 启动器和 PowerShell 入口的离线准备通过；正常服务使用默认 `.local-data/`，实际 `127.0.0.1:8770/api/health` 返回 `ok`；重复端口启动失败且未创建指定的新数据目录。测试数据只在 `.m1-build/` 内。

## 证据与复现

保存到 `work-logs/evidence/windows-2026-10-04-*.json`：开发检查、网络、安装事务完整验收、应用端到端和实际服务启动检查。安装的详细构建/迁移报告保存相应源码身份与每阶段实际加载映像哈希。`application_ready: false` 是独立原型/安装检查的范围标志，并非绕过应用失败；这些工具不批准完整发布，应用证据在独立报告中。

```powershell
.\scripts\start-local.ps1
# 已准备好后可完全离线启动
.\scripts\start-local.ps1 --offline
# PowerShell 脚本受限时
py -3 scripts/bootstrap.py

# 开发回归
.\.venv\Scripts\python.exe scripts/check_windows_native.py --network
.\.venv\Scripts\python.exe scripts/check_windows_install.py --offline
.\.venv\Scripts\python.exe scripts/check_windows_app.py
```

正常从终端启动时按 `Ctrl+C` 关闭。`--port` 与 `--data-dir` 可传给启动入口。本次交付时另外启动了后台服务供立即使用，控制台输出位于 `.m1-build/windows-app-server/`；可以用 `Get-NetTCPConnection -LocalPort 8770 -State Listen` 确认进程，关闭本次服务后再从自己的终端启动。

## 未扩大声明的范围

发布前进一步核对发现：当前 Mac 基线的 `implementation_sha256` 与共享源码计算值不一致；Mac 启动链 `start-local.sh → light_runtime.install → load_approved → verify_evidence` 会因此拒绝安装。这不是仅缺少一次人工确认，当前分支不能宣称两端都可直接启动。需要在 Mac 上完成当前源码验收并按既有流程更新基线；不手工改哈希绕过检查。

Windows 10/ARM64、完整长路径与网络盘、独立普通账户/干净虚拟机、IPv6、外部盘符竞争压力、宿主崩溃后 AppContainer profile 残留回收、全部 PDF 的逐页视觉验收和 30 次性能采样仍待补充。较长作业路径会明确拒绝，当前实测 270 字符的原生 ACL/锁路径不支持，不修改系统注册表兜底。运行库再分发许可和正式发布审批仍单独处理，下载的 EXE/DLL 不提交 Git、不上传发布。Mac 历史证据原样保留，不能当成本分支已回归的证明。
