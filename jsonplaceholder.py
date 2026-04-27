"""
examples/jsonplaceholder.py
────────────────────────────────────────────────────────────────────
示範情境：對 JSONPlaceholder（公開測試 API）進行負載測試

執行方式：
    python -m pyload -f examples/jsonplaceholder.py -u 20 -r 5 -t 30

解說：
  - host       : 目標主機（必填）
  - wait_time  : 每次 task 後等待 0.5~2 秒（模擬真實使用者行為）
  - @task(weight=N) : weight 越高越常被選到
  - on_start   : 每個虛擬使用者初始化時執行（可做登入、取 token）
  - on_stop    : 虛擬使用者結束時執行（可做清理）
"""

from pyload import HttpUser, task


class JSONPlaceholderUser(HttpUser):
    host = "https://jsonplaceholder.typicode.com"
    wait_time = (0.5, 2.0)  # 每次 task 後隨機等 0.5~2 秒

    def on_start(self):
        """每個虛擬使用者啟動前執行 — 可在這裡做登入、取得 token"""
        # resp = self.post("/auth/login", json={"user": "test", "pass": "1234"})
        # self._session.headers["Authorization"] = f"Bearer {resp.json()['token']}"
        pass

    # ── Tasks ─────────────────────────────────────────────────

    @task(weight=5)
    def list_posts(self):
        """最常執行：列表頁"""
        self.get("/posts", name="GET /posts")

    @task(weight=3)
    def get_single_post(self):
        """取單筆文章（隨機 1~100）"""
        import random
        post_id = random.randint(1, 100)
        # name 參數讓不同 id 的請求統計在同一個 task 下
        self.get(f"/posts/{post_id}", name="GET /posts/:id")

    @task(weight=2)
    def list_comments(self):
        """取留言列表"""
        self.get("/comments", name="GET /comments")

    @task(weight=1)
    def create_post(self):
        """寫入操作（低頻）"""
        resp = self.post(
            "/posts",
            name="POST /posts",
            json={"title": "load test", "body": "hello", "userId": 1},
        )
        # 可加 assertion，失敗時拋出例外讓框架記錄為錯誤
        if resp.status_code != 201:
            raise Exception(f"建立失敗: {resp.status_code}")

    @task(weight=1)
    def list_users(self):
        self.get("/users", name="GET /users")
