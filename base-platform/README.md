# 文化智能体 · 基座平台（V1.2）

公共能力底座：统一建设一次，子平台复用。

需求规格说明书（SRS V1.2）：  
`../docs/智能体基座平台软件需求规格说明书_SRS_V1.2.md`（同目录另有 `.docx`）。

## 能力清单

1. 统一身份与权限（RBAC / SSO 票据 / 企业微信 OAuth）
2. 模型网关调度（限流 / 配额 / 计费）
3. 知识库服务（**向量嵌入 + 余弦相似度 RAG** / 文档治理 / 重索引）
4. 工作流引擎（Prompt 版本 / **可视化编排器** / 灰度·A-B 路由）
5. 插件工具框架（HTTP 调用 / 市场模板 / 调用审计）
6. 安全合规审计（脱敏 / 审计 / 会话 / 合规弹窗 / **灰度与 A/B 生效**）

另附：**文化智能体子平台样板**（`/culture`）

## 启动

```bash
cd base-platform
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python run.py
```

| 入口 | 地址 |
|------|------|
| 六大能力控制台 | http://127.0.0.1:8000/ |
| 工作流可视化编排 | http://127.0.0.1:8000/workflow-editor |
| 文化子平台样板 | http://127.0.0.1:8000/culture |
| 租户管理后台 | http://127.0.0.1:8000/admin |
| API 文档 | http://127.0.0.1:8000/docs |

## 账号

| 账号 | 密码 | 用途 |
|------|------|------|
| `admin` | `admin123` | 平台管理员 |
| `demo` | `demo123` | 教育/企业样板 |

## SSO

1. 已登录基座后：`POST /api/v1/auth/sso/ticket` 拿一次性票据  
2. 子平台：`POST /api/v1/auth/sso/exchange` 兑换 token  
3. 企业微信：配置 `.env` 中 `WECOM_*`；未配置时可用 mock 回调联调  

## 向量检索说明

当前使用本地 n-gram 哈希嵌入（384 维）+ 纯 Python 余弦相似度，**无需 numpy / 外网模型**即可运行。  
上传文档时自动向量化；也可调用 `POST /api/v1/kb/repo/{repo_id}/reindex` 重建。  
后续可替换为 OpenAI Embedding / sentence-transformers / pgvector。
