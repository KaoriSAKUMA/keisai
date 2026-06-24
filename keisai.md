# /keisai：掲載通知照合（5ステップ自動実行）

スプレッドシートとSlack通知を貼り付けるだけで、5ステップの照合を一括実行します。

## 使い方

```
/keisai
■ スプレッドシート（会社名・プラン・担当）
企業名	求人登録	プラン	ランク	制作担当
（表をそのまま貼り付け）

■ Slack通知
（Slackのテキストをそのまま貼り付け）
```

---

## 受け取った情報

$ARGUMENTS

---

## 実行方針（最重要・必ず守る）

このコマンドは **「1本のPythonスクリプトを作って、1回だけ実行し、Step 1〜5の表と要確認まとめを一気に出力する」** という方式で必ず行う。

- **ステップごとに何度もBashを実行しない。** 照合は1本のスクリプトにまとめて、Bashの実行は原則1回にする（会社数が多くても1回）。
- **CSVの中身を画面に出力しない**（`print(行全体)` などで生データを垂れ流さない）。必要な項目だけ取り出す。
- 出力する表は **スクリプト自身に `print` させる**。Claudeが手で表を組み立て直さない。
- スクリプトがエラーになったら、原因を直して**もう一度実行する**。途中で止めない。
- **完了条件：Step 1〜5の5つの表と「⚠ 要確認まとめ」をすべて出力し終えるまでターンを終了しない。**

CSVフォルダ（固定）: `C:\Users\chiba\Documents\掲載通知\`
- `jp_job.csv` … 求人データ（Shift-JIS = cp932）
- `jp_company_schedule.csv` … 掲載スケジュール（UTF-8）
- `jp_contract.csv` … 契約プラン一覧（Shift-JIS = cp932）
- `jp_staff_company.csv` … 企業スタッフ紐づけ（Shift-JIS = cp932）：company_company_id × company_staff_id で照合

**CSVの読み込み・検索・照合はすべて確認不要で進める。新規作成・上書き・削除する場合のみ確認する。**

---

## 実行手順

### 手順1：入力データを解析して、スクリプトの先頭に埋め込む

$ARGUMENTS から次の2つを取り出し、下のスクリプト雛形の `SHEET = [...]` と `SLACK_TEXT = """..."""` に埋め込む。

1. 「■ スプレッドシート」以降のタブ区切り表 → 1社1行で `{"name","job_id","plan","rank","staff"}` のリストにする（「追加」行も含める）
2. 「■ Slack通知」以降のテキスト → そのまま `SLACK_TEXT` に文字列として入れる

### 手順2：下のスクリプトを1本作成し、Bashで1回だけ実行する

スクリプトは「4つのCSVを読み込み → Step 1/2/3/5の照合 → Step 4のSlack照合 → 6つの表をMarkdownでprint」を一気に行う。下を雛形として、CSVの実際の列名に合わせて調整する。

```python
# -*- coding: utf-8 -*-
import csv, os, re

BASE = r"C:\Users\chiba\Documents\掲載通知"

# ===== ここに入力を埋め込む（Claudeが $ARGUMENTS から作る）=====
SHEET = [
    # {"name": "株式会社リード", "job_id": "20230577", "plan": "プレミアム12週間", "rank": "10", "staff": "森田"},
    # {"name": "株式会社リード", "job_id": "20230578", "plan": "追加",          "rank": "10", "staff": "森田"},
    # ... 全行 ...
]
SLACK_TEXT = r"""
（■ Slack通知 以降のテキストをそのまま貼る）
"""
# 社内管理アカウント（表示は「ほか」にまとめる）
INTERNAL_STAFF_IDS = {"12303", "13476", "13877"}
# =============================================================

def load_csv(name, enc):
    path = os.path.join(BASE, name)
    with open(path, encoding=enc, newline="") as f:
        return list(csv.DictReader(f))

job_rows      = load_csv("jp_job.csv", "cp932")
sched_rows    = load_csv("jp_company_schedule.csv", "utf-8")
contract_rows = load_csv("jp_contract.csv", "cp932")
staff_rows    = load_csv("jp_staff_company.csv", "cp932")

# 列名はCSVの実物に合わせて調整すること
job_by_id     = {r.get("job_id"): r for r in job_rows}

def md_table(header, rows):
    out  = "| " + " | ".join(header) + " |\n"
    out += "|" + "|".join(["---"] * len(header)) + "|\n"
    for r in rows:
        out += "| " + " | ".join(str(c) for c in r) + " |\n"
    return out

# ---- Step 1：求人データ確認 ----
s1, company_of = [], {}
for it in SHEET:
    j = job_by_id.get(it["job_id"])
    if j:
        cid = j.get("job_company_id")
        company_of[it["job_id"]] = cid
        exist = "✓"
        pub = j.get("job_publish_time") or "（未設定）"
        if str(j.get("job_conf_publish")) != "1":
            pub += "（未承認）"
    else:
        exist, pub = "✗", "—"
    s1.append([it["name"], it["job_id"], exist, pub])

print("### ✅ Step 1：求人データ確認（jp_job.csv）\n")
print(md_table(["会社名","求人ID","CSV存在","掲載予定日時"], s1))

# ---- Step 2：スケジュール確認 ----  company_of を使って jp_company_schedule.csv を照合し contract_id を得る
# ---- Step 3：プラン・ランク照合 ----  contract_id で jp_contract.csv を照合（回数/週/+365、ランク）
# ---- Step 5：スタッフ登録確認 ----  company_id で jp_staff_company.csv を照合（spool_status=1のみ計数、社内IDは「ほか」）
# ---- Step 4：Slack照合 ----  SLACK_TEXT を解析し SHEET と突き合わせ（漏れ・回数・+365・重複・Slackのみの会社）

# 各 Step の表も上と同じく print(md_table(...)) で必ず出力する。
# 最後に「### ⚠ 要確認まとめ」の表も print する（問題なければ「異常なし」）。
```

---

## 出力フォーマット（スクリプトがprintする中身）

以下の6つを必ずすべて出力する。問題がない項目も省略しない。

### ✅ Step 1：求人データ確認（jp_job.csv）
| 会社名 | 求人ID | CSV存在 | 掲載予定日時 |
|---|---|---|---|

### ✅ Step 2：スケジュール確認（jp_company_schedule.csv）
| 会社名 | 登録 | 掲載日時 | 契約ID |
|---|---|---|---|

### ✅ Step 3：プラン・ランク照合（jp_contract.csv）
| 会社名 | スプレッドシート記載 | CSVプラン | ランク | 一致 |
|---|---|---|---|---|

### ✅ Step 4：Slack照合
| 会社名 | Slack報告 | 回数 | プラン一致 | 備考 |
|---|---|---|---|---|

### ✅ Step 5：スタッフ登録確認（jp_staff_company.csv）
| 会社名 | 登録状況 | 登録アカウントID |
|---|---|---|

### ⚠ 要確認まとめ
異常・不一致・確認が必要な事項を優先度つきで列挙する（問題がなければ「異常なし」と記載）。
| 優先度 | 会社名 | 内容 |
|---|---|---|

---

**最後に必ず確認：** スクリプトの実行結果として、Step 1〜5の5つの表と「⚠ 要確認まとめ」がすべて画面に出ているか？ 欠けていればスクリプトを直して再実行し、出し切ってから終了すること。
