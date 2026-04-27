# ⚡ PyLoad — Python 輕量級 API 負載測試工具

類 Locust 設計，純 Python 標準庫 + `requests`，無需安裝其他套件。

---

## 快速開始

```bash
# 執行範例情境（20 users，每秒新增 5 個，跑 30 秒）
python -m pyload -f examples/jsonplaceholder.py -u 20 -r 5 -t 30

# 產生 HTML + JSON 報告
python -m pyload -f myscenario.py -u 100 -r 10 -t 120 \
    --html report.html --json result.json
```

---

## CLI 參數

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `-f / --file` | 情境檔案路徑 | 必填 |
| `-u / --users` | 虛擬使用者總數 | 10 |
| `-r / --spawn-rate` | 每秒新增使用者數 | 1 |
| `-t / --run-time` | 執行秒數（0 = 無限） | 0 |
| `--interval` | Console 更新間隔（秒） | 2 |
| `--html` | HTML 報告路徑 | report.html |
| `--json` | JSON 報告路徑（空 = 不輸出）| |
| `--no-html` | 不產生 HTML 報告 | |

---

## 撰寫情境

新增一個 `.py` 檔，繼承 `HttpUser`，用 `@task` 標記測試方法：

```python
from pyload import HttpUser, task

class MyAPIUser(HttpUser):
    host = "https://api.example.com"
    wait_time = (1, 3)          # 每次 task 後等 1~3 秒

    def on_start(self):
        """每個虛擬使用者初始化（登入、取 token 等）"""
        resp = self.post("/auth/login", json={"user": "test", "pass": "secret"})
        token = resp.json()["token"]
        self._session.headers["Authorization"] = f"Bearer {token}"

    @task(weight=5)             # weight 越高越常被選到
    def get_products(self):
        self.get("/products", name="GET /products")

    @task(weight=2)
    def search(self):
        self.get("/search?q=hello", name="GET /search")

    @task(weight=1)
    def create_order(self):
        resp = self.post("/orders", json={"product_id": 1, "qty": 2})
        if resp.status_code != 201:
            raise Exception(f"下單失敗: {resp.status_code}")
```

### 重點說明

- **`host`** — 目標主機，必填
- **`wait_time`** — `(min, max)` 秒，每次 task 後的隨機等待（模擬真實使用者）
- **`@task(weight=N)`** — weight 控制被選中頻率，`weight=3` 代表是 `weight=1` 的 3 倍機率
- **`name` 參數** — 讓不同路徑的請求（如 `/posts/1`, `/posts/2`）統計在同一個 task 下
- **`self._session`** — `requests.Session` 物件，可設定 headers、auth、cookies
- **`on_start` / `on_stop`** — 生命週期 hook，每個虛擬使用者各執行一次

---

## 專案結構

```
pyload/
├── pyload/
│   ├── __init__.py      # 公開 API
│   ├── __main__.py      # python -m pyload 入口
│   ├── user.py          # HttpUser 基底類別、@task 裝飾器
│   ├── engine.py        # 負載引擎（ThreadPoolExecutor + spawn rate）
│   ├── stats.py         # 執行緒安全統計收集器
│   ├── console.py       # 即時 Console 報表
│   ├── reporter.py      # HTML + JSON 報告產生器
│   └── cli.py           # CLI 入口（argparse）
└── examples/
    └── jsonplaceholder.py   # 示範情境
```

---

## Console 報表說明

```
────────────────────────────────────────────────────────────────────────────────
 PyLoad [LIVE]  elapsed=12s  users=20  RPS=47.3  errors=0.0%
────────────────────────────────────────────────────────────────────────────────
Task                          Reqs  Fail   Err%    RPS     Avg     P50     P95     P99     Max
────────────────────────────────────────────────────────────────────────────────
GET /posts                     284     0   0.0%   23.6     312     298     521     634     891
GET /posts/:id                 172     0   0.0%   14.3     308     291     498     601     754
GET /comments                  113     0   0.0%    9.4     325     310     543     622     812
```

| 欄位 | 說明 |
|------|------|
| Reqs | 累計請求數 |
| Fail | 累計失敗數（HTTP 4xx/5xx 或例外） |
| Err% | 錯誤率（綠 <1%、黃 1~5%、紅 >5%） |
| RPS  | 最近 10 秒的每秒請求數 |
| Avg  | 平均回應時間（ms） |
| P50/P95/P99 | 百分位延遲（ms） |
| Max  | 最大延遲（ms） |
