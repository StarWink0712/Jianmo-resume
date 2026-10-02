# 简墨仓库首次源码提交

## 目标与范围

- 将当前 M0-M2 项目准备提交至用户指定的 `StarWink0712/Jianmo-resume`。
- 保留远端 `main` 的初始提交 `282492b52c7e987c174d8818b29d2d3dc94e5798` 及原 MIT 许可证，不覆盖远端历史、不强制推送。
- README 合并简墨名称与原仓库描述，补充新环境启动前提、运行时不随源码分发的边界，并纠正行高设置说明。
- 清理规划中的行尾空格与两份历史文本证据末尾的多余空行，不改变验收结果。
- 扩展忽略规则：生成物、临时文件、真实简历数据库、头像、虚拟环境、构建运行时及本地凭据不进入提交。随附字体与许可证、PDF.js 与许可证、虚构样例及脱敏文档保留。

## 发布检查

- 源码、文档、日志进行了真实身份信息、个人路径及常见凭据模式检查；未发现匹配。这不是完整的安全或再分发许可审计。
- 两张文档截图经目视检查为虚构样例；生成的 PDF 和私有截图目录均不提交。
- `git check-ignore` 确认本地数据、构建运行时、生成 PDF、临时头像、环境文件、数据库及密钥文件被排除；只改变版本控制规则，不删除本机文件。
- 使用仓库所有者的 GitHub noreply 邮箱作为本次提交身份，不发布本机默认工作邮箱，也不修改全局 Git 身份。

## 本轮测试

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/resume-library.test.cjs tests/avatar-model.test.mjs tests/markdown-model.test.mjs tests/section-model.test.mjs tests/style-model.test.mjs
```

- Python 125 项通过，Node 46 项通过。
- Python 测试出现 Starlette 对 httpx 测试客户端的弃用提示，没有测试失败；本轮不升级依赖。
- 本轮未重新执行完整 TeX 集成、安装或跨浏览器验收，没有改动运行中的编辑服务及用户简历。

## 推送状态与下一步

- 公共仓库拉取成功，已建立 `origin` 远端。
- GitHub CLI 尚未登录，HTTPS 无可用凭据；校验 GitHub 官方主机公钥后的 SSH 验证也返回公钥授权失败。
- 本批次仅形成本地源码提交，推送受授权阻断，远端尚未更新。用户需要在本机运行 `gh auth login --hostname github.com --git-protocol https --web` 完成授权，再继续普通推送并核对远端提交哈希。
- 不在聊天或日志中收集密码、访问令牌或私钥；不改变全局 SSH 信任配置。
