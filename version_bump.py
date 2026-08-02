#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""版本号 bump 工具：大改动 +100、小改动 +1，跨天重置为 .100。
用法：
    python version_bump.py major "改动原因"
    python version_bump.py minor "改动原因"
输出最终版本号。
"""
import json
import os
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(BASE, 'version.json')


def bump(kind, reason):
    kind = kind.lower()
    if kind not in ('major', 'minor'):
        print('kind 必须为 major 或 minor')
        sys.exit(1)
    today = datetime.now().strftime('%y.%m.%d')
    data = {'date': today, 'seq': 100, 'version': f'{today}.100', 'history': []}
    if os.path.exists(PATH):
        with open(PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    # 跨天重置
    if data.get('date') != today:
        data['date'] = today
        data['seq'] = 100
    else:
        if kind == 'major':
            # 当前序号向上取整到下一个百位
            data['seq'] = ((data['seq'] // 100) + 1) * 100
        else:
            data['seq'] += 1
    ver = f"{today}.{data['seq']}"
    data['version'] = ver
    data.setdefault('history', []).append({
        'date': today,
        'ver': ver,
        'type': 'major' if kind == 'major' else 'minor',
        'reason': reason or ''
    })
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(ver)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('用法: python version_bump.py [major|minor] "改动原因"')
        sys.exit(1)
    bump(sys.argv[1], sys.argv[2])
