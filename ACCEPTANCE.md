# 验收指南

本文档说明如何人工核验 cb-auto-subscribe 系统的关键业务决策和实现正确性。

---

## 一、可转债申购信息来源

系统使用四个数据源交叉验证，≥2 个来源均有记录时自动标记为 `confirmed`，仅 1 个来源的进入 `pending` 等待人工确认。

### 数据源一：AKShare 巨潮资讯（主力源）

| 项目 | 内容 |
|---|---|
| 函数 | `akshare.bond_cov_issue_cninfo(start_date, end_date)` |
| 数据来源 | 巨潮资讯（cninfo.com.cn），官方权威来源 |
| 日期格式 | `YYYYMMDD` 字符串，例如 `"20260416"` |
| 申购代码字段 | `网上申购代码` |
| 债券简称字段 | `债券简称` |
| 市场字段 | `交易市场`，值为 `上交所` → `SH`，`深交所` → `SZ` |

**人工核验步骤：**

```bash
python -c "
import akshare as ak
from datetime import date
today = date.today().strftime('%Y%m%d')
df = ak.bond_cov_issue_cninfo(start_date=today, end_date=today)
print(df[['网上申购代码','债券简称','交易市场','网上申购数量上限']].to_string())
"
```

核验点：
- 输出的申购代码、债券名称与东方财富/集思录当日显示一致
- `交易市场` 字段值为 `上交所` 或 `深交所`（非交易日输出为空 DataFrame 属正常）

---

### 数据源二：东方财富数据接口

| 项目 | 内容 |
|---|---|
| 接口 | `https://datacenter-web.eastmoney.com/api/data/v1/get` |
| 数据来源 | 东方财富网数据中心，无需 Token |
| 申购日期字段 | `VALUE_DATE`（格式 `YYYY-MM-DD HH:MM:SS`，取日期部分） |
| 申购代码字段 | `CORRECODE` |
| 债券简称字段 | `SECURITY_NAME_ABBR` |

**人工核验步骤：**

```bash
curl -s "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_BOND_CB_LIST&columns=ALL&sortColumns=PUBLIC_START_DATE&sortTypes=-1&pageSize=50&pageNumber=1&source=WEB&client=WEB" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = d.get('result', {}).get('data', []) or []
for r in rows[:5]:
    print(r.get('VALUE_DATE','')[:10], r.get('CORRECODE',''), r.get('SECURITY_NAME_ABBR',''))
"
```

核验点：
- 输出的 `CORRECODE`、`SECURITY_NAME_ABBR` 与巨潮资讯当日数据一致
- `VALUE_DATE` 格式为 `YYYY-MM-DD HH:MM:SS`（系统取前 10 位做日期匹配）

---

### 数据源三：集思录数据接口

| 项目 | 内容 |
|---|---|
| 接口 | `https://www.jisilu.cn/webapi/cb/pre/?history=N` |
| 数据来源 | 集思录（jisilu.cn），专注可转债数据 |
| 申购日期字段 | `apply_date`（格式 `YYYY-MM-DD`） |
| 申购代码字段 | `apply_cd` |
| 债券简称字段 | `bond_nm` |

**人工核验步骤：**

```bash
curl -s -H "User-Agent: Mozilla/5.0" -H "Referer: https://www.jisilu.cn/" \
  "https://www.jisilu.cn/webapi/cb/pre/?history=N" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
rows = d.get('data', []) or []
for r in rows[:5]:
    print(r.get('apply_date',''), r.get('apply_cd',''), r.get('bond_nm',''))
"
```

核验点：
- 输出的 `apply_cd`、`bond_nm` 与巨潮资讯当日数据一致
- `apply_date` 为 `YYYY-MM-DD` 格式

---

### 数据源四：人工录入

通过管理界面「快照」Tab 手动添加，用于补充其他数据源遗漏的债券。

---

## 二、支持的券商及接入方式

### 当前支持券商

| 适配器 | 文件 | 接入方式 | 状态 |
|---|---|---|---|
| miniQMT（推荐） | `app/brokers/miniqmt_adapter.py` | xtquant 官方协议接口 | 代码完成，需本地客户端 |
| 同花顺 | `app/brokers/tongtongxin.py` | easytrader 屏幕模拟 | 代码完成，不稳定 |
| Mock（测试用） | `app/brokers/mock_broker.py` | 纯内存模拟 | 测试专用 |

**东方财富：已放弃**，无可用程序化交易接口。

---

## 三、miniQMT 接入核验

### 前置条件

1. 在迅投合作券商开户（华西证券、国金证券、广发证券等）
2. 申请开通 MiniQMT 权限（联系券商客户经理）
3. 本机安装 MiniQMT 客户端并登录
4. 安装 xtquant：`pip install xtquant`

### 账户 credentials 格式

在前端创建账户时，credentials 字段填入如下 JSON：

```json
{
  "path": "C:/miniQMT/userdata_mini",
  "account_id": "你的证券账户号",
  "session_id": 123456
}
```

| 字段 | 说明 |
|---|---|
| `path` | MiniQMT 客户端的 userdata 目录路径 |
| `account_id` | 证券账户号（非资金账号） |
| `session_id` | 任意整数，区分多个连接，同一时间不要重复 |

### 人工核验步骤

```python
# 测试 miniQMT 连接
import asyncio
from app.brokers.miniqmt_adapter import MiniQMTBroker

async def test():
    broker = MiniQMTBroker()
    ok = await broker.login({
        "path": "C:/miniQMT/userdata_mini",
        "account_id": "你的账户号",
        "session_id": 123456,
    })
    print("登录:", ok)
    print("余额:", await broker.get_balance())
    print("当日委托:", await broker.query_today_orders())

asyncio.run(test())
```

核验点：
- 登录返回 `True`
- 余额与 MiniQMT 客户端界面显示一致
- 申购时 `subscribe_bond("754321", 1000)` 返回 `code=SUCCESS`，客户端有委托记录

---

## 四、账户凭证安全核验

凭证加密方式：Fernet 对称加密，密钥来自环境变量。

```bash
# 生成密钥
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 验证加解密
python -c "
import os
os.environ['ENCRYPTION_KEY'] = '填入上面生成的密钥'
from app.shared.crypto import encrypt, decrypt, get_keys_from_env
fernet, _ = get_keys_from_env()
c = encrypt('{\"account_id\": \"123456\"}', fernet)
print('加密结果:', c[:30], '...')
print('解密结果:', decrypt(c, fernet))
"
```

核验点：解密结果 = 原始 JSON 字符串。

---

## 五、自动化测试

```bash
cd /Users/jassionyang/cb-auto-subscribe
python -m pytest tests/ -v
```

预期结果：`43 passed`，无 ERROR。

测试覆盖范围：

| 测试文件 | 覆盖内容 |
|---|---|
| `test_data_sources.py` | AKShare 抓取（含字段名核验）、EastMoney 抓取、Jisilu 抓取、ManualSource、聚合器 |
| `test_calendar.py` | 交易日判断、节假日、AKShare 日历加载 |
| `test_crypto.py` | 加解密、密钥轮换 |
| `test_executor.py` | 申购去重、结果记录 |
| `test_notifier.py` | 去重窗口、飞书/企微/邮件发送 |
| `test_reconciler.py` | 对账标记 |
| `test_trigger_integration.py` | 手动触发 API 端点 |
| `test_worker_main.py` | 定时任务注册、非交易日跳过 |

---

## 六、定时任务时间表核验

```bash
python -c "
from app.worker.main import create_scheduler
s = create_scheduler()
for j in s.get_jobs():
    print(f'{j.id:15} {str(j.trigger)}')
"
```

预期输出 6 个任务：

| 任务 ID | 执行时间（北京时间） | 内容 |
|---|---|---|
| `snapshot` | 08:50 | 抓取当日可申购债券列表 |
| `warmup` | 09:20 | 预热券商连接、检查账户状态 |
| `subscribe` | 09:30:05 | 正式申购 |
| `retry_1` | 09:35 | 第一次重试失败委托 |
| `retry_2` | 10:00 | 第二次重试失败委托 |
| `reconcile` | 14:30 | 对账：比对本地记录与券商委托 |

---

## 七、已知限制

| 项目 | 说明 |
|---|---|
| miniQMT 仅支持 Windows | xtquant 客户端目前只有 Windows 版本 |
| Docker 部署不支持 miniQMT | 需要 GUI 客户端，无法容器化，建议本机部署 |
| 同花顺适配器不稳定 | 屏幕模拟方案，客户端更新后可能失效 |
| 非交易日所有任务自动跳过 | 基于 `CalendarService`，AKShare 无数据时回退静态节假日表 |
