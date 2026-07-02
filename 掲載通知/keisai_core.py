import csv, sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

data = json.loads(sys.stdin.buffer.read().decode('utf-8'))

companies = data["companies"]
slack_reports = data.get("slack_reports", [])

INTERNAL_IDS = {"12303", "13476", "13877"}
base = r"C:\Users\chiba\Documents\掲載通知"
all_ids = [i for c in companies for i in c["ids"]]
issues = []

def derive_rank(plan_str):
    p = plan_str.upper()
    if "PLUS" in p or "プラス" in plan_str:
        return "12"
    if "プレミアム" in plan_str:
        return "10"
    if "アッパー" in plan_str:
        return "8"
    if "スタンダード" in plan_str:
        return "6"
    return "10"

# ===== Step 1: jp_job.csv =====
job_map = {}
with open(f"{base}\\jp_job.csv", encoding="cp932", errors="replace") as f:
    for row in csv.DictReader(f):
        if row["job_id"].strip() in all_ids:
            job_map[row["job_id"].strip()] = row

company_id_map = {}
for c in companies:
    for jid in c["ids"]:
        if jid in job_map and c["name"] not in company_id_map:
            cid = job_map[jid].get("job_company_id", "").strip()
            if cid:
                company_id_map[c["name"]] = cid

print("## ✅ Step 1：求人データ確認（jp_job.csv）\n")
print("| 会社名 | 求人ID | CSV存在 | 掲載予定日時 |")
print("|---|---|---|---|")
for c in companies:
    for jid in c["ids"]:
        row = job_map.get(jid)
        mark = "✓" if row else "✗"
        pub = row.get("job_publish_time", "—").strip() if row else "—"
        conf = row.get("job_conf_publish", "—").strip() if row else "—"
        if not row:
            issues.append(("高", c["name"], f"求人ID {jid} がCSVに存在しない"))
        elif conf != "1":
            issues.append(("高", c["name"], f"求人ID {jid} 掲載承認未設定（conf={conf}）"))
        print(f"| {c['name']} | {jid} | {mark} | {pub} |")

# ===== Step 2: jp_company_schedule.csv =====
schedule_map = {}
with open(f"{base}\\jp_company_schedule.csv", encoding="utf-8", errors="replace") as f:
    for row in csv.DictReader(f):
        cid = row.get("schedule_company_id", "").strip()
        if cid in company_id_map.values():
            schedule_map[cid] = row

contract_id_map = {}
for name, cid in company_id_map.items():
    row = schedule_map.get(cid)
    if row:
        ctid = row.get("schedule_conf_contract_id", "").strip()
        if ctid:
            contract_id_map[name] = ctid

print("\n## ✅ Step 2：スケジュール確認（jp_company_schedule.csv）\n")
print("| 会社名 | 登録 | 掲載日時 | 契約ID |")
print("|---|---|---|---|")
for c in companies:
    name = c["name"]
    cid = company_id_map.get(name, "")
    row = schedule_map.get(cid)
    if row:
        st = row.get("schedule_time", "—").strip()
        ctid = contract_id_map.get(name, "—")
        print(f"| {name} | ✓ | {st} | {ctid} |")
    else:
        issues.append(("高", name, "スケジュール未登録"))
        print(f"| {name} | ✗ | — | — |")

# ===== Step 3: jp_contract.csv =====
target_ctids = set(contract_id_map.values())
contract_data = {}
with open(f"{base}\\jp_contract.csv", encoding="cp932", errors="replace") as f:
    for row in csv.DictReader(f):
        ctid = row.get("contract_id", "").strip()
        if ctid in target_ctids:
            contract_data[ctid] = row

print("\n## ✅ Step 3：プラン・ランク照合（jp_contract.csv）\n")
print("| 会社名 | 管理ツール記載 | CSVプラン | ランク | 一致 |")
print("|---|---|---|---|---|")
for c in companies:
    name = c["name"]
    ss_plan = c["plan"]
    ss_rank = c.get("rank") or derive_rank(ss_plan)
    ctid = contract_id_map.get(name, "")
    row = contract_data.get(ctid)
    if row:
        csv_plan = row.get("contract_name", "—").strip()
        csv_rank = row.get("contract_company_conf_rank", "—").strip()
        rank_ok = ss_rank == csv_rank
        ss_weeks = re.search(r'(\d+)週', ss_plan)
        csv_clean = re.sub(r'[（(][^）)]*[）)]', '', csv_plan)
        csv_weeks = re.search(r'(\d+)', csv_clean.replace("プレミアム","").replace("アッパー","").replace("スタンダード",""))
        ss_w = ss_weeks.group(1) if ss_weeks else ""
        csv_w = csv_weeks.group(1) if csv_weeks else ""
        plan_ok = (ss_w == csv_w) if ss_w and csv_w else True
        ok = rank_ok and plan_ok
        if not rank_ok:
            issues.append(("高", name, f"ランク不一致（SS={ss_rank} / CSV={csv_rank}）CSVプラン：{csv_plan}"))
        if not plan_ok:
            issues.append(("高", name, f"プラン週数不一致（SS:{ss_w}週 / CSV:{csv_w}週）"))
        mark = "✓" if ok else "⚠"
        print(f"| {name} | {ss_plan} | {csv_plan} | SS={ss_rank} / CSV={csv_rank} | {mark} |")
    else:
        issues.append(("高", name, f"契約ID={ctid} がCSVに存在しない"))
        print(f"| {name} | {ss_plan} | — | — | ✗ |")

# ===== Step 4: Slack照合 =====
slack_map = {r["name"]: r for r in slack_reports}
ss_names = {c["name"] for c in companies}

print("\n## ✅ Step 4：Slack照合\n")
print("| 会社名 | Slack報告 | 件数 | 担当（表／Slack投稿者） | 備考 |")
print("|---|---|---|---|---|")
for c in companies:
    name = c["name"]
    expected = len(c["ids"])
    ss_tanto = (c.get("tanto") or "").strip()
    sr = slack_map.get(name)
    if sr:
        ok = sr["count"] == expected
        cnt = f"{sr['count']}件" + ("" if ok else f" ⚠（管理ツール={expected}件）")
        if not ok:
            issues.append(("中", name, f"Slack件数不一致（報告={sr['count']} / 管理ツール={expected}）"))
        poster = (sr.get("poster") or "").strip()
        tanto_col = "—"
        if ss_tanto and poster:
            tanto_ok = (ss_tanto in poster) or (poster in ss_tanto)
            tanto_col = f"{ss_tanto} / {poster}" + ("" if tanto_ok else " ⚠")
            if not tanto_ok:
                issues.append(("中", name, f"担当者ズレ（表の制作担当={ss_tanto} / Slack投稿者={poster}）"))
        print(f"| {name} | ✓ | {cnt} | {tanto_col} | |")
    else:
        issues.append(("高", name, "Slack未報告"))
        print(f"| {name} | ✗ | — | — | 未報告 |")

for sr in slack_reports:
    if sr["name"] not in ss_names:
        issues.append(("参考", sr["name"], "SlackにあってSSに未掲載"))
        print(f"| {sr['name']} | Slackのみ | {sr['count']}件 | — | SSに未掲載 |")

# ===== Step 5: jp_staff_company.csv =====
staff_map = {}
with open(f"{base}\\jp_staff_company.csv", encoding="cp932", errors="replace") as f:
    for row in csv.DictReader(f):
        cid = row.get("company_company_id", "").strip()
        if cid in company_id_map.values():
            staff_map.setdefault(cid, []).append(row)

print("\n## ✅ Step 5：スタッフ登録確認（jp_staff_company.csv）\n")
print("| 会社名 | 登録状況 | 登録アカウントID |")
print("|---|---|---|")
for c in companies:
    name = c["name"]
    cid = company_id_map.get(name, "")
    entries = staff_map.get(cid, [])
    active = [e for e in entries if e.get("company_spool_status", "").strip() == "1"]
    real = [e["company_staff_id"].strip() for e in active if e["company_staff_id"].strip() not in INTERNAL_IDS]
    has_internal = any(e["company_staff_id"].strip() in INTERNAL_IDS for e in active)
    if real:
        id_str = ", ".join(real) + (", ほか" if has_internal else "")
        print(f"| {name} | ✓ {len(real)}件 | {id_str} |")
    elif has_internal:
        issues.append(("中", name, "内部アカウントのみ（企業スタッフ未登録）"))
        print(f"| {name} | 内部のみ | ほか |")
    else:
        issues.append(("高", name, "スタッフ未登録（企業ログイン不可）"))
        print(f"| {name} | ★未登録 | — |")

# ===== 要確認まとめ =====
print("\n## ⚠ 要確認まとめ\n")
if issues:
    print("| 優先度 | 会社名 | 内容 |")
    print("|---|---|---|")
    for pri, name, detail in issues:
        print(f"| {pri} | {name} | {detail} |")
else:
    print("異常なし")
