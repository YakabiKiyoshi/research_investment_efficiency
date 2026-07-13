# docs/papers — 参照論文 PDF

追試・引用監査・文献参照の対象となる **他者の論文 PDF** を置く標準フォルダ。

- ファイル名の慣例: `<著者>_<年>_<誌>.pdf`（例 `Foo_2020_JAR.pdf`）。
  PDF 取り込みパイプラインの `paper_id` はこのファイル名 stem になる。
- 取り込み: `powershell -File scripts\ai\run-ai-workflow.ps1 -Workflow pdf-ingest -Target docs\papers\<file>.pdf`
  （決定論ローカル抽出。アーティファクトは `outputs/ai/pdf/<paper_id>/`）。
- 消費規律は `.claude/skills/pdf-ingestion/SKILL.md` を参照（PDF 本体を
  context に読み込まず query packet 経由で使う）。

自分の原稿は `paper/` に置く（このフォルダは参照文献専用）。
