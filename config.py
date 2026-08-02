# -*- coding: utf-8 -*-
"""乾明工作台账系统 - 系统配置（公司 / 客户 / LOGO / 标题等）

集中存放以往硬编码在模板与 docx 中的公司信息，避免硬编码。
配置保存为 config.json，缺失时使用默认值。
"""
import os
import json
import secrets

from paths import EXE_DIR, RES_DIR

BASE = EXE_DIR
CONFIG_FILE = os.path.join(BASE, 'config.json')
SECRET_KEY_FILE = os.path.join(BASE, 'secret.key')

DEFAULTS = {
    'system_title': '乾明工作台账系统',
    'company_short_name': '新东升物业',
    'customer_name': '嘉应学院丰顺校区',
    'company_logo': '',          # 站点 LOGO 的 URL，如 /static/Images/logo.svg
    'docx_logo': '',             # 台账模板中嵌入的 LOGO 文件名（位于 static/Images/）
    # AI 配置（用于 AI 生成智能总结，需用户自行填写 KEY）
    'ai': {
        'provider': 'siliconflow',   # 服务商标识
        'base_url': 'https://api.siliconflow.cn/v1',  # 兼容 OpenAI 的接口地址
        'api_key': '',               # 用户申请的 API Key
        'model': 'Qwen/Qwen3-8B-Instruct',  # 当前选用的模型
    },
}

# 周期文案（智能总结用）
PERIOD_LABELS = {
    'year': '全年', 'half1': '上半年', 'half2': '下半年',
    'q1': '第一季度', 'q2': '第二季度', 'q3': '第三季度', 'q4': '第四季度',
}


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    # 注入动态版本号（由 version.json 维护，不写回 config.json）
    try:
        vfile = os.path.join(RES_DIR, 'version.json')
        with open(vfile, 'r', encoding='utf-8') as f:
            cfg['version'] = json.load(f).get('version', cfg.get('version'))
    except Exception:
        pass
    return cfg


def save_config(data):
    cfg = dict(DEFAULTS)
    cfg.update({k: data.get(k, DEFAULTS[k]) for k in DEFAULTS})
    # 保存 AI 配置（嵌套，按默认结构合并，避免覆盖缺失字段）
    saved_ai = dict(DEFAULTS.get('ai', {}))
    saved_ai.update(data.get('ai', {}) or {})
    cfg['ai'] = saved_ai
    # 原子写：先写 .tmp 再用 os.replace 替换，避免崩溃时损坏 config.json
    tmp = CONFIG_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)
    return cfg


def load_secret_key():
    """返回持久化的 Flask secret_key。

    首次运行随机生成并写入 secret.key（与 config.json 同级，属用户数据，
    更新程序不应删除），后续复用以保证重启后登录会话不失效。
    仅本机/内网可信部署使用，不依赖外部机密管理。
    """
    if os.path.exists(SECRET_KEY_FILE):
        try:
            with open(SECRET_KEY_FILE, 'r', encoding='utf-8') as f:
                key = f.read().strip()
            if key:
                return key
        except Exception:
            pass
    key = secrets.token_hex(32)
    try:
        with open(SECRET_KEY_FILE, 'w', encoding='utf-8') as f:
            f.write(key)
    except Exception:
        pass
    return key


def company_full(cfg=None):
    """组合后的公司全称，如：新东升物业（嘉应学院丰顺校区）"""
    if cfg is None:
        cfg = load_config()
    short = (cfg.get('company_short_name') or '').strip()
    cust = (cfg.get('customer_name') or '').strip()
    if cust:
        return f'{short}（{cust}）'
    return short or short
