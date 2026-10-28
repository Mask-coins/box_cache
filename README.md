# box-cache

Windows用の、過去の版を保持するファイルキャッシュです。
「プロジェクト名＋キー」で識別し、保存日時が最も新しい版を読み出します。

## インストール

WindowsとPython 3.11以降が必要です。動作確認環境はPython 3.14です。
実行時の外部依存ライブラリはありません。

使用したいPython環境から、GitHubの最新版を直接インストールできます。
事前のダウンロード・展開・Gitのインストールは不要です。

```powershell
python -m pip install "https://github.com/Mask-coins/box_cache/archive/refs/heads/master.zip"
```

IntelliJで既存の `.venv` を使っている場合は、そのPythonを明示してインストールできます。

```powershell
.\.venv\Scripts\python.exe -m pip install "https://github.com/Mask-coins/box_cache/archive/refs/heads/master.zip"
```

この例は利用先プロジェクトのルートで実行します。仮想環境の作り直しや `pyvenv.cfg` の編集は必要ありません。
ライブラリは利用するPython環境ごとにインストールし、キャッシュの保存先設定は同じWindowsユーザー内で共有します。

更新時は次を実行します。同じバージョン番号でもGitHub上の更新を取り込めるよう、再インストールを指定します。

```powershell
python -m pip install --upgrade --force-reinstall "https://github.com/Mask-coins/box_cache/archive/refs/heads/master.zip"
```

上記URLは `master` ブランチの最新内容を指します。利用する版を固定する場合は、`https://github.com/Mask-coins/box_cache/archive/<コミットSHA>.zip` の形式で対象のコミットを指定してください。
公開先は [GitHubリポジトリ](https://github.com/Mask-coins/box_cache) です。PyPIへの公開は行っていません。

## 初期設定

キャッシュ専用の、新しいディレクトリを指定してください。親ディレクトリは存在している必要があります。

```powershell
box-cache configure --cache-dir D:\my-cache
box-cache config show
```

`python -m box_cache configure --cache-dir D:\my-cache` でも実行できます。

設定は `%LOCALAPPDATA%\box_cache\config.json` に保存します。
同じWindowsユーザー・同じ `LOCALAPPDATA` なら、作業ディレクトリや仮想環境が変わっても同じ保存先を使用します。
設定変更時に既存のキャッシュを移動・削除することはありません。

同名の設定ディレクトリや保存先がすでにあり、このパッケージ用と確認できない場合は停止します。
空のディレクトリも自動では流用しません。未設定時に別の場所へ自動保存することもありません。

## 使用例

```python
import json
from box_cache import get, put

put("weather", "tokyo", '{"temperature": 20}')
text = get("weather", "tokyo")  # 保存時と同じ str
if text is not None:
    weather = json.loads(text)  # JSONのパースは呼び出し側で行う

put("images", "sample", b"\x00\x01\xff")
binary = get("images", "sample")  # bytes
```

- `put(project, key, data)` は `bytes` または `str` を保存し、成功時は `None` を返します。
- `get(project, key)` は保存時の型のデータを返します。未登録・破損時は `None` です。空文字や空のバイト列も保存できるため、存在確認には `is not None` を使ってください。
- キーは任意のPython文字列です。空文字、日本語、URL、制御文字も使えます。大文字小文字は区別します。
- プロジェクト名はWindowsのファイル名に使える名前に限定します。予約名、禁止文字、末尾の空白・ピリオドなどは使えません。
- 同じキーに対して `Weather` と `weather` のように大文字小文字だけ違うプロジェクト名を使うと停止します。読み出し時も同じ表記を使ってください。

## 保存ファイルと異常時の動作

保存先にはサブディレクトリを作りません。

```text
my-cache/
  .box_cache.json
  box_cache.log
  weather_<キーのSHA-256>_20261028T030000123Z.json
  weather_<キーのSHA-256>_20261028T030000123Z.data
  ...
```

ログは異常を記録するときに作成されます。再保存は新しい版を追加し、過去の版を保持します。
有効期限、容量制限、自動削除、過去の版を読むAPIはありません。

読み出し時に、本体のサイズとSHA-256をメタデータと照合します。
最新版が破損していたら `CacheWarning` を出し、キャッシュ直下の `box_cache.log` に記録して `None` を返します。
古い版には自動で戻りません。読めるメタデータには破損情報も記録します。
ログを書けない場合も、その失敗をワーニングで通知します。

ファイル名の日時はUTCのミリ秒精度です。同じプロジェクト・キー・ミリ秒の保存は衝突として停止します。
キャッシュへの操作はOSロックで排他制御します。並行操作が競合した場合は待たずに停止します。
保存中断で残った一時ファイルや本体も自動削除しません。
最新版の本体だけが残ってメタデータがない場合は、破損・保存中断として警告し `None` を返します。

設定・アクセス権・競合のエラーは `CacheError` の派生例外になります。
不正な引数は `TypeError` または `ValueError` です。

```python
from box_cache import CacheError, put

try:
    put("weather", "tokyo", "data")
except CacheError as error:
    print(f"保存できませんでした: {error}")
```

## 開発とテスト

開発する場合はGitでソースを取得し、使用するPython環境に編集可能な形式でインストールします。

```powershell
git clone https://github.com/Mask-coins/box_cache.git
cd box_cache
python -m pip install -e .
```

追加のテストライブラリは不要です。未インストールのソースからも実行できます。

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

テストは一時ディレクトリ内に設定とキャッシュを作成し、通常のユーザー設定を変更しません。
仕様は [docs/specification.md](docs/specification.md)、構成は [docs/architecture.md](docs/architecture.md) を参照してください。
