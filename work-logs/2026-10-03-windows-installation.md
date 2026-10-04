# Windows 路径、DLL 审计和事务安装

本页保留当日阶段状态；后续应用接入与验收见 [2026-10-04 记录](2026-10-04-windows-application.md)。

本轮承接 `894b9b3` 的原生编译原型。环境仍为 Windows 11 x64 10.0.26200、Python 3.12.6，未提权。**正式 Windows adapter 仍保持关闭；本文不代表应用已经可启动或完成发布验收。**

## 实现

- 临时运行时盘符改用没有 `OBJ_PERMANENT` 的 NT 对象管理器符号链接，由宿主持有的不继承句柄控制寿命。创建时避开现有设备名，名称冲突直接失败，不覆盖已有映射。正常退出、异常退出、宿主被强杀和同时持有多个别名的测试通过。宿主被终止后，Windows 可能稍后才完成句柄回收，测试使用有界等待。
- 不能改成任意名称的设备路径：XeTeX 可以执行 `--version`，但 Kpathsea 的资源搜索不能正常处理该路径。当前保留盘符形式，仅映射专用运行时；未放宽 `C:\Users` 的权限。此实现依赖原生 NT API，其他 Windows 版本仍需单独实测。
- 使用 Win32 调试事件检查实际 EXE/DLL 加载，包括子进程和短暂的 `LoadLibrary`。对事件提供的文件句柄计算哈希，运行时文件必须同时匹配实际路径和固定哈希，其他映像限定在 Windows System32 下。策略失败时，在继续事件前终止整个 Job。
- 实测发现“系统目录优先”会让机器上已有的 MSVCR100 替代固定版本，因此保留应用目录优先，并检查实际加载文件。错误引擎哈希和作业目录中的未批准 DLL 都在后续代码执行前被拒绝；正常系统 DLL 加载通过。
- ACL 修改改为先固定祖先目录与目标句柄，再通过句柄设置 DACL。目录扫描先拒绝 junction、重解析点和硬链接，避免递归进入外部目标。新增硬链接逃逸和祖先被重命名的测试。
- 输出预算仍是采样限制。活跃临时文件可消失或进入 delete-pending；采样允许删除共享，通过文件句柄读取实时大小，最多重试三次连续的访问忙错误，持续失败仍停止任务。不能把目录枚举缓存的大小当作正在写入文件的实际大小，也不能将采样宣称为硬磁盘配额。

## 安装事务

新增 `core/runtime_manifest.py` 和 `core/runtime_install.py`：严格跨平台归档路径、大小写冲突与 Windows 设备名/ADS 检查；与 POSIX mode 无关的文件清单；独占安装锁；不可变 `releases/<sha256>`；普通文件 `current.json`；同文件系统原子切换。

开发安装器 `scripts/install_windows_runtime.py` 只下载/复用锁定资源，在 AppContainer 中生成格式并完成三份参考简历与全部 22 项样例后才激活。安装期间源码变化会拒绝激活。现有版本不覆盖、不删除；激活记录被占用、构建或 PDF 验收失败时，旧记录保持不变。已落定但尚未激活的有效版本可在重试时复用。

安装清单包含所有运行时文件的相对路径、大小和 SHA-256，以及本次构建身份。重新使用时会重新核验清单、固定 EXE/DLL、字体和完整验收结果；发现损坏会明确失败，不悄悄换用系统 TeX。

这是**开发安装入口**，尚未接入正式后端、共享 bootstrap 或 PowerShell 用户启动脚本。Mac 安装器和旧 `current` 链接迁移没有在本轮替换。

## 验收

`scripts/check_windows_native.py --network` 实机通过：

- 共享 Python 61 项、原生 Windows 25 项、安装/路径事务 12 项，共 98 项，无跳过；前端 Node 74 项。
- 依赖、12 个生产/共享模块的非 UTF-8 默认编码导入、数据契约检查通过。
- DNS、公网 IPv4 TCP 和本机局域网地址连接在沙箱中被阻断，宿主在前后均可正常执行对应操作；本地监听器没有收到沙箱连接。loopback 正反向控制由原生套件独立验证。
- 尚未把 IPv6 或远端局域网机器标记为通过。当前进程未提权，也不等于已经在一个独立的非管理员组账户上验收。

证据与完整安装检查结果见同目录 `evidence/windows-2026-10-03-*.json`。生成的 EXE/DLL、运行时、日志和 PDF 仍只保存在忽略目录 `.m1-build/`，不提交到 Git。

## 复现

在 `project` 目录使用已有虚拟环境，不需要激活：

```powershell
# 本地测试；--network 会使用真实 DNS 和 TCP 正向控制
& .\.venv\Scripts\python.exe scripts\check_windows_native.py --network

# 开发安装：已有固定下载缓存时无需下载
& .\.venv\Scripts\python.exe scripts\install_windows_runtime.py --offline

# 完整安装、离线复用、落定目录后的重新编译验收
& .\.venv\Scripts\python.exe scripts\check_windows_install.py --offline
```

首次没有引擎缓存时去掉 `--offline`；固定包的大小和哈希仍必须匹配。三个 Windows 包共 11,755,948 bytes，不能把该下载量当成最终磁盘占用。

## 尚待完成

1. 独立普通账户、长路径、其他目标系统版本、盘符耗尽和外部盘符管理程序竞争；AppContainer profile 在宿主崩溃后的残留清理、并发编译时运行时 ACL 生命周期、压力和句柄继承验收。
2. Windows 锁的正式批准、DLL/运行库许可与分发义务、破损资源/缺失 DLL/错误架构矩阵；System32 当前作为受信系统边界，尚未缩为按用途批准的系统 DLL 子集。
3. Windows 执行器接入共享编译流程和后端；端口排他、数据目录 ACL、bootstrap 与 PowerShell 启动入口；完整业务和浏览器验收、跨平台工程迁移、全部 PDF 视觉检查与性能采样。
4. 修改影响执行实现摘要。Mac 历史批准证据原样保留，需要回到 Mac 重新验收，不能在 Windows 更新批准哈希。

## API 依据

- [Microsoft：对象生命周期](https://learn.microsoft.com/en-us/windows-hardware/drivers/kernel/life-cycle-of-an-object)
- [Microsoft：WaitForDebugEvent](https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-waitfordebugevent)
- [Microsoft：LOAD_DLL_DEBUG_INFO](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-load_dll_debug_info)
- [Microsoft：文件实时大小与 DeletePending](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_standard_info)
