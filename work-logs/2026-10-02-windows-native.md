# Windows 原生开发记录

日期：2026-10-02。交接源提交：`c87aa20`；本机导入基线：`5017503`；开发分支：`windows-native`。

## 当前结论

已从 Windows 拒绝执行占位，推进到**真实 Windows 受限编译原型**。正式应用仍未启用：`platform_adapters/windows.py` 的能力与拒绝逻辑保持原样。本记录不是 Windows 发布批准。

Mac 原交接的 177 个文件在改动前校验通过，原始清单没有修改。已建立本地 Git，无远程地址、无推送。交接后的开发验收使用下述新入口，不再用原始交接包字节校验来判断修改后的代码。

## 实测环境与结果

- Windows 11 x64，系统版本 10.0.26200；CPython 3.12.6 x64，默认文本编码 cp936。
- 进程 TokenElevation 为 false；全程未提权。尚未在独立的非管理员组账户重复验收。
- 固定 Python 依赖的 Windows wheel 安装和 `pip check` 通过，未变更依赖版本。
- 12 个正式入口的非 UTF-8 默认读取导入检查通过。
- 共享 Python 用例 61 项、Windows 原生用例 18 项通过；Node 模型用例 74 项通过。
- 真实 AppContainer 内生成格式，编译 Java、算法、测试三份参考简历；文字完整、字体嵌入且来自项目字体、无缺字、无 overfull hbox。三份参考 PDF 已逐页渲染检查，无明显重叠、乱码或裁切。
- 22 项固定样例通过：9 项实际 PDF 编译（含一页、两页、中英混排、长链接、头像、隐藏/重排模块），13 项非法数据或不支持 Markdown 被拒绝。其他样例的完整逐页视觉验收仍待完成。
- TeX 宏包、格式源、Noto 字体沿用交接中的固定资源，未安装系统 TeX、WSL 或 C++ 工具链。格式在本机受限进程中新生成，未使用 Mac `.fmt`。

`work-logs/evidence/windows-native-check.json` 保存最终共享/原生检查结果；`windows-engine-prototype.json` 保存引擎与样例结果。完整日志、PDF 与原始报告在忽略目录 `.m1-build/windows-check-*/`；JSON 保留各次真实源码摘要，不把较早的执行标记成修改后的结果。

## 新增代码

| 路径 | 用途 |
| --- | --- |
| `platform_adapters/windows_native.py` | ctypes Win32 原型：原子私有目录创建、受保护 DACL、独占文件句柄锁、每任务独立 AppContainer、挂起创建与 Job Object 关联、限制与清理 |
| `tests/test_windows_native.py` | 真实 API 正反向测试，使用临时复制的 Python 探针运行时，不修改已安装 Python 的 ACL |
| `runtime/locks/windows-x64.prototype.json` | 上游包大小/SHA-512、8 个 EXE/DLL 的大小/SHA-256、系统导入列表；明确 prototype-not-approved |
| `scripts/probe_windows_engine.py` | 固定包下载/校验、PE32+ 和普通/延迟导入检查、受限格式生成与完整样例编译；不是安装器 |
| `scripts/check_windows_native.py` | 修改后可重复运行的 Windows 开发检查，报告始终 `application_ready: false` |

原生用例覆盖：私有 DACL 及文件继承；大小写目录别名下的锁互斥；锁持有者异常退出；设备名/ADS/路径歧义拒绝；目录 junction 在修改 ACL 或加锁前拒绝；秘密文件拒绝读写；另一 AppContainer 的模拟数据库拒绝读取；运行时拒绝写入；实际可用 loopback 服务的连接阻断；内存分配受限；CPU、墙钟和输出预算；取消；父进程正常退出、宿主被强杀时的子孙清理；Job 关联失败时子进程绝不恢复执行。

## 本轮发现和处理

1. `CreateProcessW` 创建 AppContainer 的精简环境需要 `LOCALAPPDATA`，否则实机返回 WinError 203。仅加入必要变量，未继承任意 PATH。
2. Windows TeX 上游 Kpathsea 用 `FindFirstFile` 逐级枚举可执行路径，AppContainer 内访问 `C:\Users` 的枚举失败。原型采用仅映射专用运行时的临时 DOS 盘符；未放宽用户目录 ACL。正常和异常 Python 退出会精确移除自身映射，但宿主被强杀的映射恢复以及与外部程序的盘符竞争**尚未完成**，不得直接拿此实现作为正式启动方案。
3. Windows 引擎需要明确的 `XE_FONTCONFIG_PATH` 和 `XE_FC_CACHEDIR`。字体配置只指向作业的固定字体副本与私有缓存，不依赖系统字体。
4. Windows Job 的 CPU 终止时机实测较粗，加入累计 Job CPU 采样作为及时停止机制，仍保留 OS Job user-time 限制。输出大小是采样限制，不宣称为磁盘硬配额。
5. Job 内存采用 committed-memory 口径，不是 macOS RSS。Windows 返回的 peak 值可能包含失败分配尝试；测试用实际 `MemoryError` 和成功分配量确认限制，不把该峰值硬套为 RSS 或改写观测值。
6. loopback 被阻断时本机返回超时而非固定 AccessDenied。测试在操作前后确认本地监听服务可用，并确认没有接收到沙箱连接，避免把服务不可用算成隔离成功。

## 重复运行

在 `project/` 下，不需要激活虚拟环境：

```powershell
& .\.venv\Scripts\python.exe scripts\check_windows_native.py
# 同时执行引擎与全部固定样例；已有缓存时可完全不下载
& .\.venv\Scripts\python.exe scripts\check_windows_native.py --engine --offline
# 新机器尚无引擎缓存时去掉 --offline；仍校验固定大小和哈希
```

每次创建独立 `.m1-build/windows-check-*`，失败退出非零并保留日志。脚本只处理虚构样例与测试数据，不打开个人简历库。引擎档案下载量 **11,755,948 bytes**（约 11.76 MB）；不是完整安装占用，也不是 Mac 的 16.2 MB 数据。只有这三份锁定包会被下载，原型不调用全局 TeX。

## 下一阶段必需工作

1. 定稿路径方案：普通账户、中文/空格路径、长路径与盘符竞争/宿主崩溃恢复；目前临时盘符只供开发原型。
2. 审计真实动态 DLL 加载和搜索顺序、缺 DLL/污染路径/错误架构/损坏包；完成上游与 Microsoft 运行库许可核对。静态 PE 依赖闭包不能替代动态审计。
3. 增加 DNS、外网和局域网正反向探针、重解析点/硬链接/已有子文件 ACL 迁移、句柄继承与资源耗尽压力；补全安全验收后再启用正式 adapter。现有路径检查不是并发恶意修改下的完整句柄式防竞争方案。
4. 实现按平台锁、不可变 releases、`current.json`、安装锁、原子切换与失败回滚、共享 bootstrap 和 PowerShell 薄入口。不能覆盖正在使用的 EXE/DLL。
5. 接入后端、执行完整业务/Edge/Chrome 验收、Mac 工程迁移、全部 PDF 视觉检查与至少 30 次完整流水线性能采样。本轮阶段耗时不包含全部准备工作，不作为最终性能承诺。
6. Mac 旧证据原样保留。新增平台实现改变了 `implementation_hash()`，本分支不能据旧记录自动批准 Mac 运行时；需要在 Mac 上独立重新回归，不能在 Windows 手工更新批准哈希。

## 一手资料

- [Microsoft：启动 AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
- [Microsoft：Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [TeX Live：Windows 平台](https://tug.org/texlive/windows.html)
- [Kpathsea 上游路径逻辑](https://github.com/TeX-Live/texlive-source/blob/trunk/texk/kpathsea/win32lib.c)

上述文档解释实现依据；通过与否以本机报告为准。
