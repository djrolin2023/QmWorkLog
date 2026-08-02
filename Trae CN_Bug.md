# 乾明工作台账系统 - Bug 与安全问题清单

> 生成日期：2026-08-02
> 范围：除"默认监听 `0.0.0.0:8088` + 默认弱口令 admin/admin"外的全部已发现问题
> 优先级：🔴 严重 / 🟠 中等 / 🟡 轻微

---

## 一、严重问题（建议立即修复）

### 🔴 1. Flask `secret_key` 硬编码

**位置**：[app.py:51](file:///f:/Python/QmWorkLog/app.py#L51)

```python
app.secret_key = 'qm-worklog-secret-key-2026'
```

**问题**：
Flask 用该密钥签名 session cookie。密钥写死在源码，且项目开源（GitHub 公开），任何人都能用该密钥伪造一个 `session['user']='admin'` 的 cookie，**直接绕过 `login_required`**，无需账号密码即可访问全部 API（删除数据、恢复备份、改密码等）。

**修复建议**：
```python
import secrets, os
app.secret_key = os.environ.get('QM_SECRET') or secrets.token_hex(32)
```
注意：随机生成后会导致重启即下线，需持久化到 `config.json` 或单独文件。

---

### 🔴 2. 角色权限未实现（管理员/普通用户两级实际不存在）

**位置**：[app.py](file:///f:/Python/QmWorkLog/app.py) 全局

**问题**：
README 宣称"管理员 / 普通用户两级角色"，但代码中完全没有 `role` 字段、没有 `admin_required` 装饰器，`login_required` 不区分身份。任意普通账号登录后都能调用高危管理接口：

| 接口 | 风险 |
|---|---|
| `/api/users` POST | 任意添加账号 |
| `/api/users/<name>/reset` | 重置任意用户密码 |
| `/api/users/<name>` DELETE | 删除账号 |
| `/api/backup/restore` | 用恶意 zip 覆盖 `DB/`、`users.json`、`Data/` |
| `/api/config` POST | 改系统标题/公司/LOGO |
| `/api/ai/config` POST | 改 AI base_url（见 SSRF） |
| `/api/logs/delete` | 清空操作日志 |
| `/api/records/delete-all` | 删光全部台账 |

**修复建议**：
- 在 `users.json` 增加 `role` 字段（`admin` / `user`）；
- 新增 `admin_required` 装饰器；
- 覆盖所有管理类 API。

---

### 🔴 3. 密码哈希过弱

**位置**：[app.py:109-111](file:///f:/Python/QmWorkLog/app.py#L109-L111)

```python
def _hash(pw):
    return hashlib.sha256(('qm#' + pw).encode('utf-8')).hexdigest()
```

**问题**：
- SHA256 是快速哈希，单 GPU 每秒可尝试上亿次；
- 使用**静态盐** `'qm#'`，所有用户共用同一盐，彩虹表可批量预计算；
- 一旦 `users.json` 泄露（如通过备份下载接口），弱口令几秒内即可被爆破。

**修复建议**：
用 Werkzeug 自带的 `generate_password_hash` / `check_password_hash`（默认 scrypt，含每用户随机盐），并保留旧哈希做迁移。

---

### 🔴 4. SSRF：AI `base_url` 无任何校验

**位置**：[app.py `_call_ai`](file:///f:/Python/QmWorkLog/app.py) / [`api_ai_config`](file:///f:/Python/QmWorkLog/app.py)

**问题**：
`base_url` 完全由用户填入，`urllib.request.urlopen` 不校验 scheme/host。配合"无角色实现"问题，任意登录用户可让服务器替其请求：
- `http://192.168.x.x/admin`
- `http://169.254.169.254/...`（云元数据接口）

**修复建议**：
- 限制 scheme 为 `https`；
- 解析 host 后禁止指向私网/回环/链路本地地址（RFC1918、127.0.0.0/8、169.254.0.0/16 等）。

---

### 🔴 5. AI `api_key` 明文存储且明文回传前端

**位置**：[config.py](file:///f:/Python/QmWorkLog/config.py) / [api_ai_config GET](file:///f:/Python/QmWorkLog/app.py)

**问题**：
- `config.json` 中 `ai.api_key` 明文；
- GET `/api/ai/config` 把 `api_key` 原样返回前端；
- 备份下载接口未单独排除 `config.json`（虽然只备份 DB/users/Data，但 `users.json` 含密码哈希）。

**修复建议**：
- GET 接口对 `api_key` 做掩码（如 `sk-***xxxx`）；
- 保存时单独写入仅当前用户可读的文件；
- 备份压缩包内 `users.json` 的密码哈希字段考虑脱敏。

---

## 二、中等问题

### 🟠 6. 多处 `int(...)` 未做异常捕获，导致 500 而非 400

**位置**：
- [api_records](file:///f:/Python/QmWorkLog/app.py)：`int(request.args.get('year', 0))`
- [api_archive_create](file:///f:/Python/QmWorkLog/app.py)：`int(data.get('year', 0))`
- [api_export](file:///f:/Python/QmWorkLog/app.py)：同上
- [api_record_image](file:///f:/Python/QmWorkLog/app.py)：`int(request.args.get('i', 0))`

**问题**：
传入非数字会抛 `ValueError` → Flask 默认 500 + 调试堆栈。

**修复建议**：
统一用 `parse_int(value, default=0)` 包装函数。

---

### 🟠 7. `users.json` 写入非原子

**位置**：[app.py `save_users`](file:///f:/Python/QmWorkLog/app.py#L131-L134)

```python
def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f)
```

**问题**：
直接 `open(..., 'w')` 覆盖写。若写入过程中断电/崩溃，文件会被截断损坏，**所有账号都无法登录**。`config.save_config` 同样问题。

**修复建议**：
写临时文件 `users.json.tmp` 后 `os.replace` 原子替换。

---

### 🟠 8. 修改/重置密码后旧 session 仍有效

**位置**：[api_account_password](file:///f:/Python/QmWorkLog/app.py) / [api_user_reset](file:///f:/Python/QmWorkLog/app.py)

**问题**：
修改密码未让其他 session 失效。密码泄露后即使改了密码，攻击者旧 cookie 仍可继续用 30 天（`PERMANENT_SESSION_LIFETIME=timedelta(days=30)`）。

**修复建议**：
给 `session` 加一个 `pw_ver` 字段（如密码哈希前 8 位），在 `login_required` 中校验，不一致即踢下线。

---

### 🟠 9. `dashboard` 视图每次访问都触发全盘扫描

**位置**：[app.py `dashboard`](file:///f:/Python/QmWorkLog/app.py#L202-L204)

```python
try:
    db.sync_filesystem()
except Exception as e:
    app.logger.warning('自动同步索引失败: %s', e)
```

**问题**：
`sync_filesystem` 会 `os.walk` 整个 `Data/` 目录，文件多时每次刷新大屏都卡。

**修复建议**：
改为定时线程或文件变更触发，而非请求触发；或加最近一次同步时间缓存（如 30 秒内不重复扫）。

---

### 🟠 10. `upsert_record` 存在竞态

**位置**：[db.py `upsert_record`](file:///f:/Python/QmWorkLog/db.py)

**问题**：
先 `DELETE` 再 `INSERT`，未包在事务里。SQLite 默认每条语句独立事务，并发请求可能丢失记录。

**修复建议**：
显式 `BEGIN IMMEDIATE` 包裹两步操作，或用 `INSERT ... ON CONFLICT(path) DO UPDATE`。

---

### 🟠 11. CSRF 保护缺失

**位置**：全局 POST/DELETE API

**问题**：
所有 POST API 仅靠 `SESSION_COOKIE_SAMESITE='Lax'` 防护。Lax 对跨站 POST 有效，但 GET 触发的下载/导出接口（`/api/backup/download`、`/api/export`、`/api/record/download`）仍可被跨页链接触发。

**修复建议**：
引入 Flask-WTF 或自定义 CSRF token，对所有非 GET 请求强制校验 `X-CSRFToken` 头。

---

### 🟠 12. 前端 `innerHTML` 拼接用户可控数据（潜在 XSS）

**位置**：
- [page-settings.js:21](file:///f:/Python/QmWorkLog/static/js/page-settings.js#L21)
  ```js
  $('#logoPreview').innerHTML = '<img src="' + c.company_logo + '">';
  ```
- [page-logs.js:40](file:///f:/Python/QmWorkLog/static/js/page-logs.js#L40) 等多处

**问题**：
虽然 `c.company_logo` 由管理端设置（路径受控），但配合"无角色"问题，任意用户都能改。其他 `page-logs.js:40` 等也有类似拼接。

**修复建议**：
统一用 `textContent` 或对动态内容做 HTML 转义后再插入。

---

## 三、轻微问题

### 🟡 13. `_diag.py` 是调试脚本

**位置**：[_diag.py](file:///f:/Python/QmWorkLog/_diag.py)

**问题**：
读取 `Data/` 下样本 docx 并打印内容。发布时应删除或加入 `.gitignore`，避免被打包进发行版。

---

### 🟡 14. `split_monthly_docx` 性能差

**位置**：[docx_utils.py `split_monthly_docx`](file:///f:/Python/QmWorkLog/docx_utils.py)

**问题**：
在循环里每次都重新 `Document(src_path)` 加载整个源文件。月度 31 天 = 加载 31 次。

**修复建议**：
加载一次后用 `copy.deepcopy` 或重建元素树。

---

### 🟡 15. `api_backup_restore` 解压路径校验可被绕过

**位置**：[app.py `api_backup_restore`](file:///f:/Python/QmWorkLog/app.py)

```python
if '..' in arc.split('/'):
    continue
```

**问题**：
在 Windows 上，`\` 分隔的路径（如 `Data\..\..\evil`）不会被 `'/'` split 命中，可能造成 zip slip 任意写。

**修复建议**：
用 `os.path.normpath` 后校验最终绝对路径必须仍在 `BASE` 目录内：
```python
dst = os.path.normpath(os.path.join(BASE, *arc.split('/')))
if os.path.commonpath([dst, BASE]) != os.path.normpath(BASE):
    continue
```

---

### 🟡 16. 日志记录被异常吞掉

**位置**：[db.py `log_action`](file:///f:/Python/QmWorkLog/db.py)

```python
except Exception:
    pass
```

**问题**：
日志失败完全无感知，排查问题时无法定位。

**修复建议**：
至少 `print(..., file=sys.stderr)` 或写入 `app.log`。

---

## 四、优先修复顺序

| 序号 | 修复项 | 优先级 |
|---|---|---|
| 1 | `secret_key` 改为随机/配置读取 | 🔴 最高 |
| 2 | 实现角色权限校验（`admin_required`） | 🔴 高 |
| 3 | 密码哈希换成 scrypt/bcrypt | 🔴 高 |
| 4 | SSRF：限制 AI `base_url` scheme/host | 🔴 高 |
| 5 | AI `api_key` 掩码处理 | 🔴 高 |
| 6 | `save_users`/`save_config` 原子写 | 🟠 中 |
| 7 | `int()` 异常处理 | 🟠 中 |
| 8 | 修改密码后旧 session 失效 | 🟠 中 |
| 9 | `api_backup_restore` 路径校验 | 🟠 中 |
| 10 | `dashboard` 全盘扫描优化 | 🟠 中 |
| 11 | `upsert_record` 事务化 | 🟠 中 |
| 12 | CSRF token | 🟠 中 |
| 13 | 前端 XSS 转义 | 🟠 中 |
| 14 | 删除 `_diag.py` | 🟡 低 |
| 15 | `split_monthly_docx` 优化 | 🟡 低 |
| 16 | `log_action` 异常处理 | 🟡 低 |
