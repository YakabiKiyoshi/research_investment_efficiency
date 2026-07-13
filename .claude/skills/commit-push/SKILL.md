---
description: 現在のブランチの変更を単一コミットにまとめて origin の同名ブランチへプッシュする。直近の作業内容を要約した日本語コミット・メッセージを生成し、`git add .` を避けて個別ファイル指定でステージする。ユーザーが「Githubにコミットしてプッシュ」「コミット・プッシュ」「push」等と依頼したときに起動する。
---

# 変更のコミットとプッシュ

現在のワークツリーの変更（modified + untracked）を1コミットにまとめ、`origin/<current-branch>` へプッシュします。コミット・メッセージは直近の会話・作業内容・差分にもとづき**日本語**で自動生成します。

## 引数

- `$ARGUMENTS`（省略可）: コミット・メッセージ本体の追加指示（例: 件名の焦点、scope、破壊的変更の注意等）。省略時は会話履歴から要約する。

## 絶対の制約

- **`git add .` / `git add -A` は使わない**。変更ファイルを明示列挙してステージする（`.env`・credentials・大容量バイナリの誤混入防止）。
- **amend しない**。かならず新規コミット。
- **hook / 署名をスキップしない**（`--no-verify`, `--no-gpg-sign` は使わない）。hook 失敗時は原因を修正して再コミット。
- **force push しない**。通常の `git push origin <branch>` のみ。
- 機密ファイル（`.env`, `credentials*`, `*.pem`, `*_secret*` 等）が `git status` に含まれる場合は、コミット前にユーザーへ確認する。

## 手順

### Step 1. 状態確認

以下を並列で実行（Bash の複数呼出しで並列化）:

- `git status --short`（変更ファイル一覧）
- `git diff --stat`（変更規模）
- `git log --oneline -5`（メッセージ・スタイル把握）
- `git branch --show-current`（現在ブランチ）
- `git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "no-upstream"`（upstream 有無）

### Step 2. ステージするファイルの決定

`git status --short` の出力を解析:

- **含める**: 通常のソース、ドキュメント、設定、テスト、生成物（PDF, CSV, 画像）で本件に関係があるもの
- **除外（ユーザー確認）**: `.env`, `credentials*`, `*.key`, `*.pem`, `*_secret*`, `*.p12` 等。検出時はコミット前にユーザーに報告
- **注意**: 10MB 超のファイルはユーザーに事前確認

ファイル一覧を決めたら `git add <file1> <file2> ...` で明示ステージ（1回の git add コマンドで列挙可）。

### Step 3. コミット・メッセージの生成

件名（日本語、20〜50字程度）+ 空行 + 本文（任意、段落または箇条書き）を作成。

**件名の書き方**:
- **日本語**で書く。絵文字は付けない。
- 1行目で**「なぜ」**（変更の目的・動機）を簡潔に述べる。「何を変更したか」の機械的な列挙にしない。
- 「修正」「整理」「対応」「追加」「削除」など動作を表わす語で終えるのが既存スタイル。
- `$ARGUMENTS` があればそれを最優先で件名の焦点に反映。
- なければ、直近の会話・差分・`directions.txt` / `CLAUDE.md` / memory から主目的を特定。
- 既存 `git log --oneline -10` のスタイル（prefix 有無、語彙、コロン・読点の使い方）に合わせる。たとえば `proof_reading_XX 対応：…` のような既存パターンは踏襲する。

**本文の構成**（必要な場合のみ）:
- 変更の「なぜ」を優先（「何を」はコードが示す）。背景・方針・参照先（`directions.txt` の該当メモ等）を書く。
- 複数トピックが混在する場合は箇条書きで論点ごとに分離。ただし、複数の独立した変更なら**分割コミット**の必要性をユーザーに確認する（勝手に分割しない）。
- proofread/校正対応の場合は該当ラウンド番号（`proof_reading_N.txt`）を本文に明記。
- 数値結果・サンプル・サイズ・再現性情報の変更も本文で要約。
- LaTeX の数式・記号はメッセージ内ではバックスラッシュを避け `omega→Omega`, `T→tau` のように素朴に書く（コミット・ログでの視認性を優先）。

**末尾**:
- `Co-Authored-By: Claude ...` などAIを共著者として示すトレーラは**付けない**（ユーザー方針。グローバル CLAUDE.md「Git / Commits」参照）。AI利用は原稿内の開示節で示し、コミット履歴には残さない。

### Step 4. コミット実行

HEREDOC で渡す（複数行メッセージの整形のため）:

```bash
git commit -m "$(cat <<'EOF'
<件名>

<本文>
EOF
)"
```

hook 失敗時は原因を修正して**新規コミットを作り直す**（amend しない）。

### Step 5. プッシュ

- upstream あり: `git push origin <current-branch>`
- upstream なし: `git push -u origin <current-branch>`

### Step 6. ユーザーへの報告

コミット SHA（短縮7桁）、プッシュ先リモート URL、件名を1--2文で報告。

## 失敗時のトラブルシューティング

- **pre-commit hook 失敗**: 修正して再ステージ → 新規コミット（amend しない）
- **push rejected（非 fast-forward）**: force push はしない。`git pull --rebase origin <branch>` を提案してユーザー確認後に再試行
- **機密ファイル検出**: 即停止してユーザーに確認。誤ってコミットした後の場合は `git reset HEAD~1` で戻す選択肢を提示
- **upstream 未設定**: `-u` オプションで自動設定

## 使用例

```
/commit-push
```
→ 会話履歴・差分から要約した日本語件名で commit & push。

```
/commit-push proof_reading_15 対応
```
→ 「proof_reading_15 対応」を件名の焦点として commit & push。

```
Githubにコミットし、プッシュしてください。
```
→ 引数なしで起動。直近の差分から「なぜ」を抽出して件名を生成。
