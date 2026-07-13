# Shared CLAUDE.md blocks

このファイルは、各研究 repo の `CLAUDE.md` に注入される**共有ブロックの正本**です。
`scripts/sync-template-tools.ps1` が `BEGIN SHARED:<name>` / `END SHARED:<name>`
マーカーの間だけを対象 repo の `CLAUDE.md` に挿入・置換します（マーカーが無い repo では
末尾に追記）。**編集は必ずこのファイルで行い、各 repo 側のマーカー内は直接編集しない**こと。

マーカー行自体もブロックの一部として同期されます。

<!-- BEGIN SHARED:data-access (managed by research-template/scripts/sync-template-tools.ps1 — edit in research-template/docs/ai/shared-claude-blocks.md, not here) -->
## データアクセス（shared — research-template から同期）

**物理パスをハードコードしない。まず台帳を見る。総当たり探索はしない。**

- 共有データ資源（NEEDS-FinancialQUEST=FQ・eol・NEEDSディスク・EDINET XBRL・
  監査等の original 系）は `C:\Data`（レイアウト v2）にあり、`scripts/data/data_paths.py`
  の `data_path("<key>")`（R は `scripts/data/data_paths.R`）で解決する。キーの一覧・
  説明は `docs/data/data-paths.json` と `docs/data/data-catalog.md`（全 repo 同期済み）。
  ルート上書きは環境変数 `RESEARCH_DATA_ROOT`。
- **別プロジェクトの成果物を使うときも同じ台帳で解決する**（キー接頭辞 `xproj_`）。
  例: `data_path("xproj_peer_weights_dir")`。台帳に無い依存を新たに使う場合は、
  ハードコードせず research-template の `docs/data/data-paths.json` にキーを追加して
  sync で配布する（root=project のパスとして登録）。
- 方法論の参照: `Methodology` リポジトリ（ローカル `project/Methodology`、GitHub
  同名）。`data_path("methodology_dir")`。手法名で `Methodology/README.md` を grep →
  該当フォルダの原典 PDF/ノートを読む。
- 発見手順: `py scripts/data/data_paths.py`（全キーの解決可否を表示）。どの repo が
  稼働中かは `project/data-pipeline/tools/project-status.ps1`。
- データ本体は GitHub に置かない（容量・ライセンス）。`data/`・`outputs/` は git 管理外。
  バックアップは Google Drive（`data-pipeline/backup/`）。
<!-- END SHARED:data-access -->
