# box-cache

Windows用のPythonファイルキャッシュです。プロジェクト名とキーを指定して文字列やバイト列を保存し、保存日時が最も新しい版を読み出せます。
再保存しても過去の版を残すため、保存内容を後からエビデンスとして確認できます。

## インストール

WindowsとPython 3.11以降が必要です。動作確認環境はPython 3.14です。

```powershell
python -m pip install "https://github.com/Mask-coins/box_cache/archive/refs/heads/master.zip"
```

GitHubから直接インストールします。Gitのインストールやリポジトリのcloneは不要です。
PyPIには公開していません。

## 初期設定

キャッシュ専用の保存先を設定します。初回は、まだ存在しないディレクトリを指定してください。親ディレクトリは必要です。

```powershell
python -m box_cache configure --cache-dir C:\Data\box_cache
python -m box_cache config show
```

`box-cache configure` / `box-cache config show` でも実行できます。

設定は `%LOCALAPPDATA%\box_cache\config.json` に保存します。
同じWindowsユーザー・同じ `LOCALAPPDATA` なら、作業ディレクトリや仮想環境が変わっても同じ保存先を使用します。
パッケージ自体は、利用するPython環境ごとにインストールしてください。
設定変更時に既存のキャッシュを移動・削除することはありません。

同名の設定ディレクトリや保存先がすでにあり、このパッケージ用と確認できない場合は停止します。
空のディレクトリも自動では流用しません。未設定時に別の場所へ自動保存することもありません。

## 使い方

```python
import box_cache

# 文字列を保存して読み出す
box_cache.put("weather", "tokyo", "晴れ")
text = box_cache.get("weather", "tokyo")
print(text)  # 晴れ

# バイト列も同じ操作で扱える
box_cache.put("images", "sample", b"\x00\x01\xff")
binary = box_cache.get("images", "sample")

# キャッシュがない場合は None
missing = box_cache.get("weather", "unknown")
```

| 操作 | 動作 |
| --- | --- |
| `box_cache.put(project, key, data, *, attributes=None)` | `str` または `bytes` と任意の付加情報を、新しい版として保存する。成功時は `None` |
| `box_cache.get(project, key)` | 保存日時が最も新しい版を、保存時と同じ型で返す。未登録・破損時は `None` |
| `box_cache.get_with_attributes(project, key)` | 同じ最新版の `(本体, 付加情報の辞書)` を返す。未登録・破損時は `None` |

プロジェクトが異なれば、同じキーでも別のキャッシュです。
空文字・空のバイト列も保存できるため、データの存在確認には `is not None` を使います。

JSONは文字列として保存し、必要に応じて呼び出し側でパースします。

```python
import json
import box_cache

box_cache.put("weather", "tokyo-json", '{"temperature": 20}')
text = box_cache.get("weather", "tokyo-json")
if text is not None:
    weather = json.loads(text)
```

### 本体と付加情報をまとめて保存・取得する

取得元のURLやステータスなどを、本体と一緒に保存できます。
HTTPアクセス自体は呼び出し側で行います。

```python
import box_cache

url = "https://example.com/"
box_cache.put(
    "web",
    url,
    b"<html>example</html>",
    attributes={
        "schema_version": 1,
        "url": url,
        "status": 200,
        "headers": {"content-type": "text/html"},
    },
)

result = box_cache.get_with_attributes("web", url)
if result is not None:
    body, attributes = result
    status = attributes["status"]
```

`get_with_attributes()` は、本体と付加情報を同じ版からまとめて読み出すため、読み出しの間に版がずれることはありません。
従来の `get()` は、本体だけを返します。
付加情報を指定せずに保存したキャッシュや、付加情報に未対応の旧形式のキャッシュでは、辞書は `{}` になります。

付加情報は、JSONで内容を変えずに保存・復元できる辞書です。キーは文字列、値には文字列・整数・有限の小数・真偽値・`None`・リスト・辞書を使えます。
バイト列、タプル、任意のPythonオブジェクト、循環参照、NaN・無限大、JSON変換で変わるサロゲートペアなどは受け付けません。
保存日時やハッシュなどの管理メタデータとは別の領域に保存します。付加情報の項目の意味や、その変更時の互換性は呼び出し側で管理してください。

### プロジェクト名とキー

- キーは任意のPython文字列です。空文字、日本語、URL、制御文字も使えます。大文字小文字は区別します。
- プロジェクト名はWindowsのファイル名に使える名前に限定します。予約名、禁止文字、末尾の空白・ピリオドなどは使えません。
- 同じキーに対して `Weather` と `weather` のように大文字小文字だけ違うプロジェクト名を使うと停止します。読み出し時も同じ表記を使ってください。

## 保存とエラーの扱い

保存先にはサブディレクトリを作りません。

```text
C:\Data\box_cache\
  .box_cache.json
  box_cache.log
  weather_<キーのSHA-256>_20261028T030000123Z.json
  weather_<キーのSHA-256>_20261028T030000123Z.data
  ...
```

再保存は新しい版を追加し、過去の版を保持します。

読み出し時に、本体のサイズとSHA-256をメタデータと照合します。
最新版が破損していたら `CacheWarning` を出し、キャッシュ直下の `box_cache.log` に記録して `None` を返します。
古い版には自動で戻りません。読めるメタデータには破損情報も記録します。
ログは異常発生時に作成します。

設定・アクセス権・競合のエラーは `CacheError` の派生例外になります。
不正な引数は `TypeError` または `ValueError` です。

```python
import box_cache

try:
    box_cache.put("weather", "tokyo", "data")
except box_cache.CacheError as error:
    print(f"保存できませんでした: {error}")
```

### 初期版の制限

- 有効期限、容量制限、自動削除はありません。過去の版が蓄積します。
- 過去の版の一覧・指定読み出しAPI、削除APIはありません。
- 日時はUTCのミリ秒精度です。同じプロジェクト・キー・ミリ秒の保存は衝突として停止します。
- 同時アクセスが競合した場合は、待機せず停止します。

## 更新

GitHubの最新内容を取り込むには、次を実行します。同じバージョン番号でも更新を反映できるよう、再インストールを指定しています。

```powershell
python -m pip install --upgrade --force-reinstall "https://github.com/Mask-coins/box_cache/archive/refs/heads/master.zip"
```

上記URLは `master` ブランチの最新版を指します。版を固定する場合は、`https://github.com/Mask-coins/box_cache/archive/<コミットSHA>.zip` を指定してください。

## ドキュメント

- [動作仕様](docs/specification.md)
- [ディレクトリ構成](docs/architecture.md)
- [開発・テスト手順](docs/development.md)
- [不具合報告](https://github.com/Mask-coins/box_cache/issues)
