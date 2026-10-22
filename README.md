# dotfiles

macOS・Windows・WSL向けの個人設定をmiseで管理する。
各環境でその環境のmiseを実行し、対応する設定を反映する。
リリースの採用に1週間の待機期間を設定し、mise自身の自動更新も有効にする。

## 導入

mise 2026.10.17以上を用意し、リポジトリをローカルディスクに取得する。
必要な既存設定は原本へ取り込んでから配置する。

暗号化したデータを利用する環境では、Google Driveに保存した`miseのdotfilesの秘密鍵.txt`を`~/.config/mise/`へ配置する。
秘密鍵は各環境で共用し、公開鍵と暗号化したデータをこのリポジトリで管理する。
macOS・WSLでは配置時に秘密鍵の権限を`600`に整える。
暗号化ファイルの名前やコード内の参照名には、内容と無関係な名前を使う。
秘密情報を設定へ埋め込む場合は、ageで暗号化した`[vars]`から参照する。

```text
mise trust
mise bootstrap --dry-run
mise bootstrap
```

## 更新

設定の編集は`.mise/conf.d`内の原本で行う。
設定内容が同じ場合は原本を共用し、OSごとの配置先を`variants`で指定する。
リポジトリを更新した後、各環境でリポジトリ直下から実行する。

```text
mise bootstrap
```

miseで宣言できる処理は設定に書く。
独自処理が必要になった場合は`[tasks.bootstrap]`からuvでPythonを実行する。

導入にはmiseの[bootstrap](https://mise.jdx.dev/bootstrap.html)、配置には[dotfiles](https://mise.jdx.dev/dotfiles.html)を使う。
