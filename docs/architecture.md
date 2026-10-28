# ディレクトリ構成と役割

更新日: 2026-10-28

本書は合意した実装時の構成を示す。動作仕様は [specification.md](specification.md) を参照する。
以下は実装予定の構成であり、すべてのファイルが作成済みであることを示すものではない。

## ソースコード

Pythonパッケージは `src` 構成とする。

```text
box_cache/
├─ pyproject.toml
├─ README.md
├─ docs/
│  ├─ specification.md
│  └─ architecture.md
├─ src/
│  └─ box_cache/
│     ├─ __init__.py
│     ├─ cache.py
│     ├─ config.py
│     ├─ metadata.py
│     ├─ storage.py
│     ├─ exceptions.py
│     └─ cli.py
└─ tests/
   ├─ test_cache.py
   ├─ test_config.py
   └─ test_storage.py
```

| ファイル | 役割 |
| --- | --- |
| `pyproject.toml` | パッケージ情報、ビルド設定、依存関係、CLIの定義 |
| `README.md` | 利用者向けのインストール、初期設定、使用方法 |
| `docs/specification.md` | 動作仕様、制約、未決定事項 |
| `docs/architecture.md` | ディレクトリ構成と実装上の役割分担 |
| `src/box_cache/__init__.py` | `put`、`get` などの公開APIの窓口 |
| `src/box_cache/cache.py` | 保存・読み出しの処理の組み立て、最新版の選択 |
| `src/box_cache/config.py` | 固定位置の設定の読み書き、保存先の検証、初期設定 |
| `src/box_cache/metadata.py` | メタデータの構造、型情報、サイズとハッシュによる検証 |
| `src/box_cache/storage.py` | ファイル操作、一時ファイル、公開手順、排他制御、上書き防止 |
| `src/box_cache/exceptions.py` | 例外とワーニングの定義 |
| `src/box_cache/cli.py` | 設定・設定表示コマンド |
| `tests/` | 保存・読み出し、設定、破損、競合などの動作検証 |

ログなどの処理は、独立させる必要が生じた段階でモジュールを追加する。
内部モジュールの分割は、公開APIと動作仕様を保ちながら実装に合わせて調整できる。

## 実行時のファイル

設定とキャッシュは、ソースコードやパッケージのインストール先から独立して配置する。

```text
%LOCALAPPDATA%\box_cache\
└─ config.json

設定したキャッシュ保存先\
├─ <識別ファイル>
├─ <ログファイル>
├─ <プロジェクト名>_<キーのハッシュ>_<保存日時>.json
├─ <プロジェクト名>_<キーのハッシュ>_<保存日時>.data
└─ ...
```

キャッシュ保存先にサブディレクトリは作らない。一時ファイルや排他制御にファイルを使う場合も直下に置く。
識別ファイル、ログ、一時ファイルなどの具体的な名前は、実装時に決定して仕様書へ反映する。
