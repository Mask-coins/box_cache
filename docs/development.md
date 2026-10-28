# 開発・テスト手順

## 開発用インストール

Windows / Python 3.11以降とGitを使用します。動作確認環境はPython 3.14です。
開発に使用するPython環境で、次を実行してください。

```powershell
git clone https://github.com/Mask-coins/box_cache.git
cd box_cache
python -m pip install -e .
```

## テスト

標準ライブラリの `unittest` を使用します。追加のテストライブラリは不要です。
リポジトリのルートで実行します。

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -B -m unittest discover -s tests -v
```

テストは一時ディレクトリに設定とキャッシュを作成し、通常のユーザー設定を変更しません。
保存・読み出し、履歴保持、破損検出、ファイル名の衝突、プロジェクト名の表記、プロセス間の排他制御などを検証します。

## 配布物の作成

```powershell
python -m pip wheel --no-deps --wheel-dir dist .
```

生成したwheelを別の検証用Python環境へインストールして確認できます。
ビルド時は `pyproject.toml` に記載されたビルド用の依存関係を使用します。実行時の外部依存ライブラリはありません。

## 設計資料

- [動作仕様](specification.md)
- [ディレクトリ構成と役割](architecture.md)
