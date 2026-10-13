# dotfiles

macOS・Windows・WSL向けの個人設定をmiseで管理する。
各環境でその環境のmiseを実行し、対応する設定を反映する。
リリースの採用に1週間の待機期間を設定し、mise自身の自動更新も有効にする。

## 導入

mise 2026.10.0以上を用意し、リポジトリをローカルディスクに取得する。
必要な既存設定は原本へ取り込んでから配置する。

```text
mise trust
mise bootstrap --dry-run
mise bootstrap
```

## 更新

設定の編集は`.mise/conf.d`内の原本で行う。
リポジトリを更新した後、各環境でリポジトリ直下から実行する。

```text
mise dot apply
```

導入用の配置定義を変更したときやリポジトリを移動したときは、`mise bootstrap`を再実行する。

miseで宣言できる処理は設定に書く。
独自処理が必要になった場合は`[tasks.bootstrap]`からuvでPythonを実行する。

導入にはmiseの[bootstrap](https://mise.jdx.dev/bootstrap.html)、配置には[dotfiles](https://mise.jdx.dev/dotfiles.html)を使う。
