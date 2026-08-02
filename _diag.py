import docx_utils as du
import os
import glob

# 找一个现有 docx
cands = []
for root in ['安保', '消控', 'Data']:
    for f in glob.glob(os.path.join(root, '**', '*.docx'), recursive=True):
        cands.append(f)
        if len(cands) >= 5:
            break
    if len(cands) >= 5:
        break

print("找到样本:", cands[:5])
for p in cands[:3]:
    print("\n==== 文件:", p)
    try:
        info = du.parse_daily(p)
        print(
            "date:",
            info.get('date'),
            "| dept:",
            info.get('dept'),
            "| images:",
            info.get('images'))
        print("content repr:", repr(info.get('content'))[:300])
    except Exception as e:
        print("解析异常:", e)
        import traceback
        traceback.print_exc()
