# 论文工具箱 — Ubuntu 服务器完整部署（含 API 与知网）

适用：**阿里云 ECS** 等，**Ubuntu 22.04**，已能 **SSH** 登录。

## 密钥与知网在本项目里如何工作

| 内容 | 作用 |
|------|------|
| **`QWEN_API_KEY` 等** | `config.py` 从 **环境变量** 或 **`st.secrets`** 读取，供各模块调用通义千问。 |
| **`CNKI_COOKIES`** | `app.py` 启动时写入项目根目录 **`cnki_cookies.txt`**（该文件已在 `.gitignore`）。 |
| **知网「自动刷新」** | `modules/reference/searcher/cnki.py`：搜索前检测 Cookie；失效时用 **`CNKI_USERNAME` + `CNKI_PASSWORD`** 调知网登录接口，成功后 **写回 `cnki_cookies.txt`**。凭据来源：`st.secrets` 或 **`cnki_credentials.json`**（二选一即可，推荐 Secrets）。 |

部署时只需在服务器放好 **`.streamlit/secrets.toml`**（不要提交到 Git），即可同时满足 **LLM API** 与 **知网自动登录**，无需你手工改 Cookie 文件。

**模板**：仓库内 **`.streamlit/secrets.toml.example`** → 复制为 **`.streamlit/secrets.toml`** 后填写。

```bash
cd ~/paper-toolbox/.streamlit
cp secrets.toml.example secrets.toml
nano secrets.toml   # 填入 QWEN_API_KEY、CNKI_USERNAME、CNKI_PASSWORD 等
chmod 600 secrets.toml
```

`secrets.toml` 最小可用示例（按你实际填写）：

```toml
QWEN_API_KEY = "你的 DashScope / 通义密钥"

# 知网：二选一或同时填；Cookie 可先留空，只靠账号密码自动登录
CNKI_COOKIES = ""
CNKI_USERNAME = "你的知网账号"
CNKI_PASSWORD = "你的知网密码"
```

可选：`QWEN_BASE_URL`、`QWEN_MODEL` 与本地 `config.py` 默认值一致时可不写。

---

## 1. 安全组

入方向放行 **TCP `22`**、**`8501`**（或你自定义端口）。

---

## 2. 上传项目

```powershell
scp -r "d:\论文\paper-toolbox" 用户@服务器IP:/home/用户/
```

---

## 3. Python 与依赖

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
cd ~/paper-toolbox
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

按上一节创建并编辑 **`~/paper-toolbox/.streamlit/secrets.toml`**。

---

## 4. 前台启动（验证）

```bash
cd ~/paper-toolbox
source .venv/bin/activate
streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --browser.gatherUsageStats false
```

浏览器访问：`http://服务器公网IP:8501`。

---

## 5. 后台常驻（systemd）

以用户 **`ubuntu`**、项目路径 **`/home/ubuntu/paper-toolbox`** 为例，请改成你的用户名与路径：

```bash
sudo nano /etc/systemd/system/paper-toolbox.service
```

写入：

```ini
[Unit]
Description=Paper Toolbox Streamlit
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/paper-toolbox
Environment=PATH=/home/ubuntu/paper-toolbox/.venv/bin
ExecStart=/home/ubuntu/paper-toolbox/.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

说明：密钥放在 **`WorkingDirectory` 下的 `.streamlit/secrets.toml`**，无需再写进 unit 文件。

```bash
sudo systemctl daemon-reload
sudo systemctl enable paper-toolbox
sudo systemctl start paper-toolbox
sudo systemctl status paper-toolbox
```

查看日志：`journalctl -u paper-toolbox -f`

---

## 6. 可选：用环境变量代替 secrets（高级）

若希望密钥不进文件而由 systemd 注入，可在 `[Service]` 增加：

```ini
EnvironmentFile=/home/ubuntu/paper-toolbox/.env
```

`.env` 中一行一个：`QWEN_API_KEY=...`。`config.py` 已优先读环境变量。知网账号仍以 **`st.secrets` 或 `cnki_credentials.json`** 为准；若也要走环境变量，需自行在启动脚本里导出后再启动（当前代码未读 `CNKI_*` 环境变量，建议仍用 `secrets.toml`）。

---

## 7. 常见问题

- **LLM 报错无密钥**：检查 `secrets.toml` 中 `QWEN_API_KEY` 或环境变量。
- **知网不自动登录**：确认 `CNKI_USERNAME` / `CNKI_PASSWORD` 已写入 `secrets.toml` 且应用已重启；或放置格式正确的 `cnki_credentials.json`（`{"username":"...","password":"..."}`）。
- **打不开网页**：安全组、本机 `ufw`、云厂商 ACL 是否放行端口。
