# cb-auto-subscribe

A股可转债自动申购系统。每个交易日自动抓取当日可申购债券、驱动多个证券账户完成申购、并在收盘后对账。

---

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    定时调度（APScheduler）              │
│  08:50 快照  09:20 预热  09:30 申购  09:35/10:00 重试  │
│                    14:30 对账                         │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   数据源层          执行层          通知层
   AKShare        Executor       飞书 / 企微
   巨潮资讯        Reconciler     邮件
   人工录入
         │             │
         ▼             ▼
      数据库（PostgreSQL）
      bond_snapshots / subscriptions / accounts / config
         │
         ▼
   Web 管理界面（FastAPI + Alpine.js）
```

---

## 核心流程

1. **08:50 快照**：调用 AKShare `bond_cov_issue_cninfo` 抓取巨潮资讯当日申购列表，写入 `bond_snapshots` 表。两个及以上数据源均有记录的债券自动标记为 `confirmed`，仅一个来源的进入 `pending`（需人工确认）。

2. **09:20 预热**：登录所有启用账户，检查资金余额，提前建立券商连接。

3. **09:30 申购**：对每个 `confirmed` 债券 × 每个启用账户，调用券商接口顶格申购，结果写入 `subscriptions` 表。

4. **09:35 / 10:00 重试**：对状态为 `FAILED` 且 `retryable=True` 的委托重试（最多2次）。

5. **14:30 对账**：查询券商当日委托，将本地状态更新为 `RECONCILED` 或 `FAILED`，发送汇报通知。

---

## 支持券商

| 券商 | 适配器 | 接入方式 | 要求 |
|---|---|---|---|
| miniQMT 合作券商（华西/国金/广发等） | `MiniQMTBroker` | xtquant 官方协议接口 ✅ | 本机安装 MiniQMT 客户端 |
| 同花顺 | `TonghuashunBroker` | easytrader 屏幕模拟 ⚠️ | 本机安装同花顺客户端 |

> **注意**：miniQMT 仅支持 Windows。Docker 部署不支持券商适配器，建议本机直接运行。

---

## 快速启动

### 本机部署（推荐，支持 miniQMT）

```bash
# 1. 克隆项目
git clone <repo> && cd cb-auto-subscribe

# 2. 安装依赖
pip install -r requirements.txt
pip install xtquant          # miniQMT 支持

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填写：
#   DATABASE_URL=sqlite+aiosqlite:///./cb.db   （本机用 SQLite 即可）
#   ENCRYPTION_KEY=<用下面命令生成>
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. 初始化数据库
alembic upgrade head

# 5. 启动服务
uvicorn app.web.main:app --reload --port 8000
```

浏览器打开 `http://localhost:8000` 进入管理界面。

### Docker 部署（仅 Web + 数据库，不含券商）

```bash
cp .env.example .env   # 填写配置
docker compose up -d
```

服务地址：`http://localhost:8080`

---

## 环境变量说明

| 变量 | 必填 | 说明 |
|---|---|---|
| `DATABASE_URL` | ✅ | 数据库连接串。本机用 `sqlite+aiosqlite:///./cb.db`，生产用 PostgreSQL |
| `ENCRYPTION_KEY` | ✅ | Fernet 密钥，用于加密券商账户密码 |
| `ENCRYPTION_KEY_OLD` | 否 | 密钥轮换时填旧密钥，平时留空 |
| `FEISHU_WEBHOOK_URL` | 否 | 飞书机器人 Webhook，留空则不发飞书通知 |
| `WECHAT_WEBHOOK_URL` | 否 | 企业微信机器人 Webhook |
| `SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD / SMTP_TO` | 否 | 邮件通知配置 |
| `DRY_RUN` | 否 | `true` 时只记录日志不实际下单，默认 `false` |
| `LOG_LEVEL` | 否 | 日志级别，默认 `INFO` |

---

## 添加账户

在管理界面「账户」Tab 中，点击「添加账户」，credentials 字段按以下格式填写 JSON：

**miniQMT 账户：**
```json
{
  "path": "C:/miniQMT/userdata_mini",
  "account_id": "你的证券账户号",
  "session_id": 123456
}
```

**同花顺账户：**
```json
{
  "exe_path": "C:/同花顺/同花顺.exe",
  "comm_password": "通讯密码"
}
```

凭证提交后自动加密存储，明文不落库。

---

## 数据模型

| 表 | 用途 |
|---|---|
| `accounts` | 券商账户，含加密凭证、熔断状态 |
| `bond_snapshots` | 每日可申购债券列表，来源和确认状态 |
| `subscriptions` | 每笔申购委托记录，含状态和重试次数 |
| `config` | 系统配置键值对 |
| `audit_logs` | 操作审计日志 |
| `app_logs` | 应用运行日志 |

---

## 熔断机制

账户连续失败 ≥ 3 次时自动熔断（`circuit_broken=True`），停止对该账户下单，发送告警通知。人工检查账户状态后，在管理界面手动恢复。

---

## 运行测试

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
# 预期：41 passed
```

详细验收步骤见 [ACCEPTANCE.md](ACCEPTANCE.md)。
