# Enterprise RAG Knowledge Assistant 作品集交付验收报告

验收日期：2026-09-05  
验收范围：代码检查、本地运行验证、API 流程验证、权限行为验证、评估问题验证、交付文件检查。未做公开部署，未发送任何外部消息。

## 1. 核心流程

已执行检查：

- 使用临时 SQLite 与 Chroma 目录启动应用测试实例，验证新文档上传、解析、索引、问答、引用展示。
- 验证文档更新后重新索引为新版本，目标文档引用版本从 v1 变为 v2，未再引用该文档旧版本。
- 验证文档删除后，针对该文档唯一内容的问题返回 `insufficient_evidence`，且 citations 为空。
- 使用 24 个固定问题覆盖正常问答、同义改写、无答案、权限隔离和引用支撑。
- 人工核对样本文档原文，确认主要演示答案由 citation excerpt 支撑。

结果：

- 上传、解析、索引、问答、引用展示：通过。
- 更新后旧版本不再作为目标文档被引用：通过。
- 删除后目标文档不可检索：通过。
- 无答案问题返回 `I do not have enough information in the available documents to answer this reliably.`：通过。

修复项：

- 调整检索 token 处理，过滤泛词并仅在问题侧做少量同义扩展，避免无答案或越权问题因 `company`、`employees`、`after` 等泛词命中无关文档。
- Chroma 语义检索不再返回 0 分结果，避免无关文档进入 citations。
- 新增删除后不可检索的回归测试。

## 2. 访问控制

已执行检查：

- 检查 `/api/chat`、`/api/documents`、`/api/chat/logs`、上传、更新、删除接口权限行为。
- 验证 HR、IT、PM demo 用户只能检索和列出自己可访问的 confidential 样本文档。
- 验证 admin demo 用户可以管理文档并查看所有日志。
- 验证非 admin demo 用户上传、修改、删除文档返回 403。
- 验证日志接口对非 admin 只返回该用户自己的查询记录。

结果：

- 问答检索过滤：通过。
- 文档列表过滤：通过，已修复。
- 查询日志过滤：通过，已修复。
- 上传、修改、删除管理权限：通过，已修复为 admin-only demo 操作。
- 未授权内容不会出现在答案、引用或 retrieved chunks：固定问题矩阵通过。

修复项：

- `/api/documents?user_id=...` 按 demo 用户过滤文档。
- `/api/chat/logs?user_id=...` 非 admin 只返回本用户日志。
- `/api/documents/upload`、`PATCH /api/documents/{id}`、`DELETE /api/documents/{id}` 要求 admin demo user。
- 前端保留 demo user selector，并明确标注为 simulated identity，不是真实身份认证。
- 启动时修复旧本地数据库中样本文档 ACL 元数据，防止旧数据仍以 `internal` 暴露给所有 employee demo 用户。

剩余限制：

- 这是 demo 级访问控制，没有真实登录、session、JWT、密码、租户隔离或审计不可篡改能力。

## 3. 真实 AI 与回退模式

已执行检查：

- 检查 OpenAI Embeddings 与 Chat 调用路径。
- 在无 `OPENAI_API_KEY` 环境下验证本地 hash embedding 与 extractive fallback 可工作。
- 验证 `/api/ai/status` 返回当前运行模式、模型名和 active embedding collection。
- 前端显示当前为 OpenAI verified、OpenAI configured but not verified，或 local fallback mode。

结果：

- 当前环境没有可用 OpenAI 凭证，真实 OpenAI Embeddings 与 Chat 调用：未验证。
- 本地回退模式：通过。
- 缺少凭证时真实调用状态标注为未验证：通过。
- embedding collection 命名逻辑：代码检查通过，本地 collection 为 `knowledge_chunks`，OpenAI collection 使用模型名 hash 生成。
- API 失败回退逻辑：代码检查通过，OpenAI embedding/chat 异常时回退到本地模式并记录状态；未用真实 API 故障做线上验证。

## 4. Docker、README 与敏感数据

已执行检查：

- `pytest backend/tests`：23 passed。
- `npm run build`：通过。
- `PYTHONPATH=backend python backend/scripts_run_evaluation.py`：通过，hit rate 1.0，MRR 1.0，citation coverage 1.0。
- 本地后端曾通过 `uvicorn` 启动并返回 `/api/health`、`/api/ai/status`、文档列表、问答响应。
- 使用同一临时 SQLite/Chroma 路径模拟应用重启，上传文档重启后仍存在并可检索。
- 检查 README 启动步骤、API 概览和配置说明，并补充 demo 权限参数与 AI 状态说明。
- 扫描 Git 跟踪文件和提交文件列表中的密钥特征、private key、password、secret、client secret。

结果：

- README 本地启动步骤：可复现。
- Docker Compose：未验证。当前机器没有 `docker` 命令，无法实际执行 `docker compose up --build`、服务就绪、容器重启和 Docker volume 持久化检查。
- 数据持久化：应用层 SQLite/Chroma 持久化模拟通过；Docker volume 持久化未验证。
- 敏感信息扫描：未发现真实密钥、真实客户资料或 private key。命中过的内容仅为 README 占位配置名和测试里的 `test-key`。

## 5. 固定评估问题结果

| 场景 | 用户 | 问题摘要 | 结果 |
| --- | --- | --- | --- |
| 正常 | HR | planned vacation advance notice | answered, Employee Handbook |
| 正常 | IT | severity one escalation | answered, IT Operations Manual |
| 正常 | PM | Project Orion next milestone | answered, Project Orion Brief |
| 正常 | HR | remote work | answered, Employee Handbook |
| 正常 | IT | production backups | answered, IT Operations Manual |
| 正常 | PM | Project Orion risk | answered, Project Orion Brief |
| 同义 | HR | scheduled PTO / time off | answered, Employee Handbook |
| 同义 | IT | critical outage escalation | answered, IT Operations Manual |
| 同义 | PM | delivery checkpoint for Orion | answered, Project Orion Brief |
| 无答案 | HR | cafeteria menu | insufficient_evidence |
| 无答案 | IT | stock price target | insufficient_evidence |
| 无答案 | PM | Tokyo weather | insufficient_evidence |
| 权限隔离 | HR | IT severity one escalation | insufficient_evidence |
| 权限隔离 | IT | HR vacation policy | insufficient_evidence |
| 权限隔离 | PM | HR vacation policy | insufficient_evidence |
| Admin | admin | HR vacation policy | answered |
| Admin | admin | IT severity one escalation | answered |
| Admin | admin | Project Orion milestone | answered |
| 引用 | HR | manager vacation approval | answered, Employee Handbook |
| 引用 | IT | incident commander duties | answered, IT Operations Manual |
| 引用 | PM | Orion dependency/risk | answered, Project Orion Brief |
| 无答案 | HR | employee benefits | insufficient_evidence |
| 同义 | IT | restore testing cadence | answered, IT Operations Manual |
| 权限隔离 | PM | IT backup handling | insufficient_evidence |

## 6. 适合演示的场景

- 以 HR demo user 提问 vacation notice，展示答案、引用 excerpt、版本号。
- 切换 IT demo user 提问同一个 HR 问题，展示 insufficient evidence，说明权限过滤发生在检索和引用前。
- 切换 Knowledge Admin 上传一个 IT confidential 文档，再切回 IT 提问并展示新文档引用。
- Admin 修改该文档元数据后再次提问，展示引用版本升级。
- Admin 删除该文档后再次提问，展示 insufficient evidence。
- 展示侧栏 AI mode：无 key 时是 Local fallback mode；有 key 但未成功调用前不会宣称 verified。

## 7. 剩余限制

- 未验证真实 OpenAI API 调用，因为当前环境没有可用凭证。
- 未验证 Docker Compose，因为当前环境没有 Docker。
- 该 demo 不是生产认证系统；demo user selector 只是模拟身份。
- 本地 fallback 的回答是抽取式，表达质量和同义泛化能力有限，适合演示 RAG 流程、权限过滤和引用，不适合作为生产问答质量证明。
