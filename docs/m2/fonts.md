# 随项目分发的统一字体

界面及 PDF 统一为 **Noto Sans CJK SC 2.004** 中文普通体/粗体（与思源黑体同源），搭配同系列 **Noto Sans 2.008** 西文四个字形。
它是接近原界面的开源无衬线方案，不是苹方或 Avenir Next 的复制品。
原界面使用的苹果字体不能因为开发机有安装就随软件直接分发。

## 一致性保证

- 原始 OTF/TTF、OFL 1.1 原文和来源说明位于 `assets/fonts/`，纳入项目资源，不从 CDN 加载。
- 版本、大小和 SHA-256 固定于 `experiments/m1/fonts.py`；构建、启动和每次编译核对资源。缺失或损坏直接报错，不回退到宋体或系统字体。
- 安装器包含六份字体和许可，使用新版本 `m1-local-20261001-noto-2.004`，保留旧安装版本。
- M2 从实际编译运行时的 `tex/fonts/` 提供字体接口，CSS 仅用本地 URL，不使用 `local()`。中英文使用同系列字族；没有字体安装步骤。
- 字体加载失败时页面明确显示警告；浏览器临时替代字体不被当作加载成功。六个字体文件都检查加载结果。
- XeLaTeX 显式使用文件路径；编译沙箱禁止读取系统字体。生成后验证实际字体名称、嵌入及 Unicode 映射。
- 字体契约/模板/运行时参与 PDF 缓存指纹，新字体不会误用旧 PDF 缓存。旧 PDF 可保留，但须重新预览才是新版。
- Markdown 中文斜体固定倾斜，西文使用真实斜体；箭头/数学符号使用 CJK 文件。PDF 内嵌字形，收件人无需安装字体。

六份字体合计 35,692,628 字节；保留完整字库避免仅为示例内容裁剪后遗漏其他人的姓名。
独立西文字体保留 ASCII `-` 与不换行连字符的不同 Unicode 映射，避免 CJK 字库的共用字形导致复制文本变化。
不承诺覆盖全部 Unicode 字符，例如不支持的 emoji 仍会明确报错。
跨平台浏览器抗锯齿可能略有差别，同一字体不等于界面逐像素相同。

## 复现验证

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m experiments.m1.build_runtime
.venv/bin/python -m experiments.m1.validate_managed
/bin/sh output/runtime/install-runtime.sh --prefix "$PWD/.m1-build/local-install"
.venv/bin/python scripts/check_backend.py
```

安装回归将程序搬至中文/空格目录、禁网，阻断全局 TeX/Python、源码字体及系统字体读取后，
重新生成虚构样例。报告见 `docs/m1/managed-results.json`。
后端回归验证字体 HTTP 响应字节与固定哈希一致，且 PDF 内嵌同一字族。
浏览器需刷新后确认 `Resume Sans`、`Resume Latin` 共六个 FontFace 状态为 `loaded`，提示文本实际使用该字体组合，且字体警告不可见。
本轮已实测通过；页面根节点的 `data-font-status="loaded"`、`data-font-faces="6"` 仅在 Font Loading API 全部成功后写入，便于诊断与回归检查。

## 验证边界

目前安装包只针对 macOS arm64；M2 后端尚未装入 M1 冻结安装包，仍是项目 Python 启动。
这次解决字体可携带性，不代表完整应用已经通过跨机器发布验收。
干净 macOS 验收仍按用户决定跳过；Windows、Linux、Intel Mac 未通过安装验证。
OFL 原文与版权随字体保留，不代表引擎和全部第三方依赖的再分发审核已完成。
