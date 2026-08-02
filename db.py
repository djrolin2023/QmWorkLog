# -*- coding: utf-8 -*-
"""SQLite 数据层：台账类型与记录元数据。
docx 实体文件仍保存在原目录 Data/[类型]/[年]/[月]/ 下，
数据库仅维护类型定义与记录索引（含内容摘要），便于模糊查询。
"""
import os
import re
import sqlite3
import logging

from docx import Document
from paths import EXE_DIR

logging.basicConfig(
    filename=os.path.join(EXE_DIR, 'app.log'),
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    encoding='utf-8',
)
db_logger = logging.getLogger('qm_worklog_db')

BASE = EXE_DIR
DB_DIR = os.path.join(BASE, 'DB')
DB_PATH = os.path.join(DB_DIR, 'worklog.db')
DATA_DIR = os.path.join(BASE, 'Data')

# 兼容旧版本：数据库原先放在项目根目录，自动迁移到 DB 目录
_OLD_DB_PATH = os.path.join(BASE, 'worklog.db')
os.makedirs(DB_DIR, exist_ok=True)
if os.path.exists(_OLD_DB_PATH) and not os.path.exists(DB_PATH):
    try:
        __import__('shutil').move(_OLD_DB_PATH, DB_PATH)
    except OSError:
        DB_PATH = _OLD_DB_PATH


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _extract_content(path):
    """从 docx 提取“工作内容”单元格文本（供模糊查询）。"""
    try:
        d = Document(path)
        t = d.tables[0]
        for row in t.rows:
            cells = list(dict.fromkeys(row.cells))
            if cells and '工作内容' in cells[0].text:
                return cells[1].text.strip()[:500]
    except Exception:
        pass
    return ''


def init_db():
    conn = _conn()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS ledger_types(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        sort INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        year INTEGER,
        month INTEGER,
        path TEXT NOT NULL,
        content TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY(type_id) REFERENCES ledger_types(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_records_type ON records(type_id);
    CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
    CREATE INDEX IF NOT EXISTS idx_records_content ON records(content);
    CREATE TABLE IF NOT EXISTS operation_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        user TEXT DEFAULT '',
        action TEXT NOT NULL,
        target TEXT DEFAULT '',
        detail TEXT DEFAULT '',
        ip TEXT DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_logs_ts ON operation_logs(ts);
    CREATE INDEX IF NOT EXISTS idx_logs_action ON operation_logs(action);
    ''')
    sync_filesystem(conn)
    conn.commit()
    conn.close()


def sync_filesystem(conn=None):
    """扫描 Data 目录，将尚未入库的台账 docx 同步进 records 表。
    每次启动与应用关键操作后调用，确保数据大屏等统计与磁盘文件一致。
    已入库的记录跳过 docx 内容解析（不再重读磁盘），仅新文件需要解析，显著加快启动。"""
    own = conn is None
    if own:
        conn = _conn()
    try:
        if not os.path.isdir(DATA_DIR):
            return
        for name in sorted(os.listdir(DATA_DIR)):
            p = os.path.join(DATA_DIR, name)
            if os.path.isdir(p) and not name.startswith('_'):
                conn.execute('INSERT OR IGNORE INTO ledger_types(name) VALUES(?)', (name,))
        types = {r['name']: r['id'] for r in conn.execute('SELECT id,name FROM ledger_types')}
        # 先取出已入库的 path 集合，避免重复解析已存在文件
        existing = {r['path'] for r in conn.execute('SELECT path FROM records')}
        for tname, tid in types.items():
            tdir = os.path.join(DATA_DIR, tname)
            for root, _dirs, files in os.walk(tdir):
                for f in files:
                    if not f.endswith('.docx') or f.startswith('~') or f.startswith('.'):
                        continue
                    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', f)
                    if not m:
                        continue
                    y, mo, d = m.groups()
                    full = os.path.join(root, f)
                    path = os.path.relpath(full, BASE).replace('\\', '/')
                    if path in existing:
                        continue  # 已入库，跳过耗时解析
                    content = _extract_content(full)
                    conn.execute(
                        'INSERT OR IGNORE INTO records(type_id,date,year,month,path,content) '
                        'VALUES(?,?,?,?,?,?)',
                        (tid, f'{y}-{mo}-{d}', int(y), int(mo), path, content))
    finally:
        if own:
            conn.commit()
            conn.close()


# ---------------- 类型 ----------------
def get_types():
    conn = _conn()
    rows = conn.execute('SELECT id,name,sort FROM ledger_types ORDER BY sort,id').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_type(name):
    name = (name or '').strip()
    if not name:
        return False, '类型名称不能为空'
    conn = _conn()
    try:
        conn.execute('INSERT INTO ledger_types(name) VALUES(?)', (name,))
        conn.commit()
        tid = conn.execute('SELECT id FROM ledger_types WHERE name=?', (name,)).fetchone()['id']
    except sqlite3.IntegrityError:
        conn.close()
        return False, f'类型「{name}」已存在'
    conn.close()
    return True, tid


def rename_type(tid, name):
    name = (name or '').strip()
    if not name:
        return False, '类型名称不能为空'
    conn = _conn()
    try:
        conn.execute('UPDATE ledger_types SET name=? WHERE id=?', (name, tid))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False, f'类型「{name}」已存在'
    conn.close()
    return True, tid


def delete_type(tid):
    """删除类型：清理 DB 记录，并把文件系统目录移入 Data/_removed 备份（不丢失历史）。"""
    conn = _conn()
    row = conn.execute('SELECT name FROM ledger_types WHERE id=?', (tid,)).fetchone()
    if not row:
        conn.close()
        return False, '类型不存在'
    name = row['name']
    conn.execute('DELETE FROM ledger_types WHERE id=?', (tid,))
    conn.commit()
    conn.close()
    src = os.path.join(DATA_DIR, name)
    if os.path.isdir(src):
        bak = os.path.join(DATA_DIR, '_removed')
        os.makedirs(bak, exist_ok=True)
        dst = os.path.join(bak, f'{name}_{int(__import__("time").time())}')
        try:
            os.rename(src, dst)
        except Exception:
            pass
    return True, name


# ---------------- 记录 ----------------
def add_record(type_id, date, path, content=''):
    conn = _conn()
    y, mo, _d = (date.split('-') + ['', ''])[:3]
    conn.execute(
        'INSERT INTO records(type_id,date,year,month,path,content) VALUES(?,?,?,?,?,?)',
        (type_id, date, int(y) if y else None, int(mo) if mo else None, path, content))
    conn.commit()
    conn.close()


def delete_record_by_path(path):
    conn = _conn()
    conn.execute('DELETE FROM records WHERE path=?', (path,))
    conn.commit()
    conn.close()


def list_records(type_id=None, year=None, month=None):
    conn = _conn()
    sql = 'SELECT r.id,r.date,r.path,r.content,t.name AS type_name FROM records r ' \
          'JOIN ledger_types t ON t.id=r.type_id WHERE 1=1'
    params = []
    if type_id:
        sql += ' AND r.type_id=?'
        params.append(type_id)
    if year:
        sql += ' AND r.year=?'
        params.append(year)
    if month:
        sql += ' AND r.month=?'
        params.append(month)
    sql += ' ORDER BY r.date DESC'
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search(keyword):
    """模糊查询：匹配类型名或记录日期/内容。"""
    kw = f'%{keyword}%'
    conn = _conn()
    sql = '''SELECT r.id,r.date,r.path,r.content,t.name AS type_name
             FROM records r JOIN ledger_types t ON t.id=r.type_id
             WHERE t.name LIKE ? OR r.date LIKE ? OR r.content LIKE ?
             ORDER BY r.date DESC'''
    rows = conn.execute(sql, (kw, kw, kw)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_records_range(type_name, start, end):
    """按日期区间查询记录（含起止），start/end 形如 'YYYY-MM-DD'。
    type_name 为 None 时跨全部类型。"""
    conn = _conn()
    sql = '''SELECT r.id,r.date,r.path,r.content,t.name AS type_name
             FROM records r JOIN ledger_types t ON t.id=r.type_id
             WHERE r.date >= ? AND r.date <= ?'''
    params = [start, end]
    if type_name:
        names = [n.strip() for n in type_name.split(',') if n.strip()]
        if len(names) == 1:
            sql += ' AND t.name=?'
            params.append(names[0])
        elif names:
            ph = ','.join(['?'] * len(names))
            sql += f' AND t.name IN ({ph})'
            params.extend(names)
    sql += ' ORDER BY r.date ASC'
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------- 统计（数据大屏） ----------------
def stats_by_type():
    """各类型台账数量，降序。"""
    conn = _conn()
    rows = conn.execute(
        'SELECT t.name AS name, COUNT(*) AS c FROM records r '
        'JOIN ledger_types t ON t.id=r.type_id GROUP BY t.id ORDER BY c DESC'
    ).fetchall()
    conn.close()
    return [{'name': r['name'], 'count': r['c']} for r in rows]


def stats_monthly():
    """最近 12 个月（含 0 值）的台账数量，按月份升序。"""
    from datetime import date
    conn = _conn()
    rows = conn.execute(
        'SELECT year, month, COUNT(*) AS c FROM records GROUP BY year, month'
    ).fetchall()
    conn.close()
    d = {(r['year'], r['month']): r['c'] for r in rows}
    today = date.today()
    out, y, m = [], today.year, today.month
    for _ in range(12):
        out.append({'month': f'{y:04d}-{m:02d}', 'count': d.get((y, m), 0)})
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    out.reverse()
    return out


def stats_summary():
    """汇总指标：台账总数、类型数、今日/本周/本月新增。"""
    from datetime import date, timedelta
    conn = _conn()
    today = date.today()
    today_s = today.strftime('%Y-%m-%d')
    week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
    month_start = today.strftime('%Y-%m-01')
    total = conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]
    type_count = conn.execute(
        'SELECT COUNT(DISTINCT type_id) FROM records').fetchone()[0]
    today_new = conn.execute(
        'SELECT COUNT(*) FROM records WHERE date >= ?', (today_s,)).fetchone()[0]
    week_new = conn.execute(
        'SELECT COUNT(*) FROM records WHERE date >= ?', (week_start,)).fetchone()[0]
    month_new = conn.execute(
        'SELECT COUNT(*) FROM records WHERE date >= ?', (month_start,)).fetchone()[0]
    conn.close()
    return dict(total=total, type_count=type_count, today_new=today_new,
                week_new=week_new, month_new=month_new)


def recent_records(n=10):
    """最新 n 条台账（类型/日期/摘要）。"""
    conn = _conn()
    rows = conn.execute(
        'SELECT r.date, r.content, t.name AS type_name FROM records r '
        'JOIN ledger_types t ON t.id=r.type_id ORDER BY r.date DESC LIMIT ?', (n,)
    ).fetchall()
    conn.close()
    return [{'date': r['date'], 'type_name': r['type_name'],
             'content': (r['content'] or '')[:120]} for r in rows]


def stats_totals():
    """汇总卡片数据：总记录数 / 类型数 / 本月新增。"""
    from datetime import date
    conn = _conn()
    total = conn.execute('SELECT COUNT(*) AS c FROM records').fetchone()['c']
    types = conn.execute('SELECT COUNT(*) AS c FROM ledger_types').fetchone()['c']
    today = date.today()
    this_month = conn.execute(
        'SELECT COUNT(*) AS c FROM records WHERE year=? AND month=?',
        (today.year, today.month)).fetchone()['c']
    conn.close()
    return {'total': total, 'types': types, 'this_month': this_month}


def type_id(name):
    conn = _conn()
    row = conn.execute('SELECT id FROM ledger_types WHERE name=?', (name,)).fetchone()
    conn.close()
    return row['id'] if row else None


def upsert_record(type_id, date, path, content=''):
    conn = _conn()
    conn.execute('DELETE FROM records WHERE path=?', (path,))
    y, mo, _d = (date.split('-') + ['', ''])[:3]
    conn.execute(
        'INSERT INTO records(type_id,date,year,month,path,content) VALUES(?,?,?,?,?,?)',
        (type_id, date, int(y) if y else None, int(mo) if mo else None, path, content))
    conn.commit()
    conn.close()


def rebuild_index():
    """重建索引：清空 records 表（保留类型定义）与 SQLite 索引，重新扫描文件系统生成。
    返回重建后的记录数。"""
    conn = _conn()
    try:
        conn.execute('DROP INDEX IF EXISTS idx_records_type')
        conn.execute('DROP INDEX IF EXISTS idx_records_date')
        conn.execute('DROP INDEX IF EXISTS idx_records_content')
        conn.execute('DELETE FROM records')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_records_type ON records(type_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_records_date ON records(date)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_records_content ON records(content)')
        sync_filesystem(conn)
        conn.commit()
        cnt = conn.execute('SELECT COUNT(*) FROM records').fetchone()[0]
        return cnt
    finally:
        conn.close()


# ---------------- 操作日志 ----------------

def log_action(user, action, target='', detail='', ip=''):
    """记录一条操作日志（登录/删除/编辑/新增等）。"""
    try:
        conn = _conn()
        conn.execute(
            'INSERT INTO operation_logs(user,action,target,detail,ip) VALUES(?,?,?,?,?)',
            (user or '', action or '', target or '', detail or '', ip or ''))
        conn.commit()
        conn.close()
    except Exception as e:
        # 日志写入失败不应影响主流程，但需落盘便于排查
        db_logger.error('log_action failed: user=%s action=%s err=%s',
                        user, action, e)


def recent_logs(limit=50, action=None, user=None, start=None, end=None):
    """查询操作日志，支持按操作类型/用户/时间区间筛选。"""
    conn = _conn()
    sql = 'SELECT id,ts,user,action,target,detail,ip FROM operation_logs WHERE 1=1'
    params = []
    if action:
        sql += ' AND action=?'
        params.append(action)
    if user:
        sql += ' AND user=?'
        params.append(user)
    if start:
        sql += ' AND ts>=?'
        params.append(start)
    if end:
        sql += ' AND ts<=?'
        params.append(end)
    sql += ' ORDER BY ts DESC LIMIT ?'
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_logs():
    conn = _conn()
    n = conn.execute('SELECT COUNT(*) FROM operation_logs').fetchone()[0]
    conn.close()
    return n


def delete_logs(action=None, user=None, start=None, end=None):
    """删除操作日志。可组合 action/user/start/end 条件；若全部为空则清空整表。
    返回被删除的条数。"""
    conn = _conn()
    sql = 'DELETE FROM operation_logs WHERE 1=1'
    params = []
    if action:
        sql += ' AND action=?'
        params.append(action)
    if user:
        sql += ' AND user=?'
        params.append(user)
    if start:
        sql += ' AND ts>=?'
        params.append(start)
    if end:
        sql += ' AND ts<=?'
        params.append(end)
    cur = conn.execute(sql, params)
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


if __name__ == '__main__':
    init_db()
    print('types:', get_types())
