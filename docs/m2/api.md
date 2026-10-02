# M2 Loopback API

基址为启动时打印的 `http://127.0.0.1:<port>`。无 CORS。除健康检查外，每次 API 请求需要 `X-Resume-Token`；所有写请求还需匹配的 `Origin`。使用 `GET /api/session` 加 `X-Resume-Bootstrap: 1` 在同源页面初始化会话，不能放在第三方网页中调用。

JSON 使用 `Content-Type: application/json`，拒绝重复字段、非有限数值及未知请求字段。错误通常为 `{code,message}`，修订冲突额外返回 `current_revision`。数据结构沿用 [M0 契约](../m0/data-contract.md)。

| 方法 | 路径 | 请求 / 返回 |
| --- | --- | --- |
| GET | `/api/health` | `status`、阶段、编译实现指纹，不返回路径或个人数据 |
| GET | `/api/session` | 当前实例随机令牌 |
| GET | `/api/resumes` | 按最近保存排序的摘要列表 |
| POST | `/api/resumes` | `{title,kind:"blank"或"sample"}`；201 详情 |
| GET | `/api/resumes/{id}` | 详情：`resume,latest_job,pdf,build_key` |
| PUT | `/api/resumes/{id}` | `{expected_revision,resume}`；更新内容并返回实际提交的修订 |
| PATCH | `/api/resumes/{id}` | `{expected_revision,title}`；重命名 |
| DELETE | `/api/resumes/{id}` | JSON `{expected_revision}`；逻辑删除，无回收站 |
| POST | `/api/resumes/{id}/copy` | `{expected_revision,title,version:"saved"或"draft",draft?}`；201 独立副本 |
| PUT | `/api/resumes/{id}/avatar?expected_revision=N` | PNG/JPEG 原始字节，类型 `application/octet-stream`；返回新修订 |
| POST | `/api/resumes/{id}/compile` | `{expected_revision}`；202 任务，可能复用已成功任务 |
| GET | `/api/jobs/{id}` | 任务状态、修订、构建键、页数及安全错误说明 |
| GET | `/api/jobs/{id}/pdf` | 成功 PDF 字节，内联；失败任务返回 409 |
| GET | `/api/jobs/{id}/pdf?download=true` | 相同字节，仅改下载响应头 |
| GET | `/api/resumes/{id}/backup?expected_revision=N` | `.resume.zip`；必须匹配当前修订 |
| POST | `/api/import` | ZIP 字节，类型 `application/zip`；201 新副本 |

`resume` 的 `id/revision/created_at/updated_at` 是服务端字段，保存时必须原样传回。成功后采用返回值，不能在客户端自行递增修订。无内容变化的保存不增加修订。

任务状态为 `queued/running/succeeded/failed/timed_out/cancelled`。任务不接受用户传入 TeX 或命令。`pdf` 是最新修订的成功任务摘要，可能与当前 `build_key` 不同：这代表旧 PDF，不代表当前内容已成功编译。

PDF 响应包含 `X-Resume-Revision` 和 `X-Build-Key`。浏览器以带令牌的 fetch 获取后转成 Blob，交给本地 PDF.js；不能把带令牌的 URL 嵌到第三方查看器。

常用状态码：403 来源/令牌错误；404 不存在；409 版本冲突、源正在编译或 PDF 未就绪；413 过大；415 类型不符；422 数据/备份非法；429 队列满；503 本地存储写入失败。503 不能显示“已保存”。
