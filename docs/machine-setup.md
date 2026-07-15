# 別 PC での環境セットアップ手順

前提: Claude Code / Codex CLI・R・Python・git・gh は導入済み。
Python・R・TeX はホスト環境で直接実行する。
データレイアウトは v2（正本 `C:\Data`、カタログ: `docs/data/data-catalog.md`）。

## 1. リポジトリ取得

```powershell
gh auth login          # 初回のみ（GitHub アカウント: YakabiKiyoshi）
mkdir $env:USERPROFILE\Documents\project
cd $env:USERPROFILE\Documents\project
gh repo clone YakabiKiyoshi/<research_リポジトリ名>
```

- 単一プロジェクトを動かすだけなら、その repo だけで足りる
  （共有スキル・`scripts/data/` ヘルパー・`docs/data/` 台帳は sync 済みコピーが同梱）。
- データの取得・更新（FQ 自動運転、EDINET DL 等）をするときは `data-pipeline` も clone。
- 共有ファイルを編集するときだけ `research-template` を clone
  （instance repo での直接編集は hook がブロックする）。

## 2. データ復元（Google Drive バックアップから）

初回のみ `rclone config` で認証（remote 名は **gdrive**、Storage: drive、
client_id 等は空欄で可）。その後:

```powershell
# 方法A: 全部復元（staging を除く全体、~260GB）
rclone copy gdrive:Backup/Data C:\Data --fast-list --transfers 8

# 方法B: プロジェクトが使う分だけ復元（推奨）
rclone copy gdrive:Backup/Data/audit C:\Data\audit
rclone copy gdrive:Backup/Data/fq/processed/AccountingExp.csv C:\Data\fq\processed\
```

- 必要ファイルの特定: repo 内を `data_path("` で検索するか、repo の
  `docs/data-sources.md` を参照。キー→パス対応は `docs/data/data-paths.json`。
- 外付け HDD で `C:\Data` を丸ごとコピーしても同じ。
- そのマシンをバックアップ元にもする場合は
  `data-pipeline\backup\register-backup-task.ps1` を一度実行
  （毎日 critical / 毎週日曜 full の定期タスクが登録される）。
  ※二重バックアップになるので、常用機 1 台だけで登録すること。

## 3. 環境変数（既定の場所に置くなら不要）

`C:\Data` と `~\Documents\project` に置くなら設定不要。別の場所に置いた場合のみ:

```powershell
setx RESEARCH_DATA_ROOT "D:\Data"
setx RESEARCH_PROJECT_ROOT "D:\project"
```

WSL から使う場合は `/mnt/c/Data` 等を同じ環境変数で渡す。

## 4. 動作確認

```powershell
cd <repo>
py scripts\data\data_paths.py     # 使うキーが [OK] になっているか（[--] は未復元）
```

R 側: `source("scripts/data/data_paths.R"); data_path("fq_accounting_exp")`。

## 5. Claude Code / Codex を使うときの注意

- repo 内の `.claude/skills/` は git で一緒に来る。モデルルーティングは
  repo ではなく、ユーザーの Codex にインストールされた `codex-orchestration`
  プラグインで管理する。
- Claude Code の**自動メモリは PC ローカル**（`~\.claude\projects\...\memory\`）。
  新しい PC の初回セッションではデータ配置の記憶がないので、
  最初に「`docs/data/data-catalog.md` を読んで」と指示すると速い。
- API キー類（`EDINET_API_KEY` 等）は git に入っていない。必要になったら
  その PC の環境変数に設定する。
- `project\CLAUDE.md`（プロジェクトルートの案内）は git 管理外。必要ならこのファイルと
  data-catalog.md を参照して手で再作成する。

## 6. データを更新する場合（data-pipeline）

- FQ: `C:\Data\fq\material\` の企業リストを FQ アプリで更新 →
  `fq/nfq_generators/*.py` で .nfq 生成 → FQ アプリで自動運転 →
  `fq/concat/` で結合 → `fq/merge/`・`fq/stock/` の R で processed を再生成。
  手順書: `data-pipeline/docs/自動運転の工程.pdf`。
- EDINET: `data-pipeline/edinet/download_edinet_reports.py`（`EDINET_API_KEY` 必要）。
- 更新後は backup タスクが夜間に Google Drive へ差分同期する。
