# Blokus Builder - 導入・使用ガイド

## 概要

Blokus Builder は Blender アドオンです。
Blokus互換の **逆溝方式**（ボード＝凸リブ、ピース裏＝凹溝）のボードとピースを、UIパネルからパラメータ調整しながら生成し、STLとして書き出せます。

---

## 1. 動作環境

| 項目 | 要件 |
|------|------|
| Blender | **3.6 LTS 以上**（推奨: 4.x） |
| OS | Windows / macOS / Linux |
| 想定プリンタ | FDM 0.4mm ノズル（初期値はこれに合わせて設定済み） |

---

## 2. インストール

### 方法A: Blender UI からインストール

1. Blender を起動
2. **Edit > Preferences > Add-ons** を開く
3. 右上の **Install...** ボタンをクリック
4. `blokus_builder.py` を選択して **Install Add-on** を押す
5. 一覧に「**Blokus Builder (Reverse Groove)**」が表示されるので、チェックボックスを **ON** にする

### 方法B: スクリプトフォルダに直接配置

1. Blender のアドオンフォルダに `blokus_builder.py` をコピーする
   - **Windows**: `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`
   - **macOS**: `~/Library/Application Support/Blender/<version>/scripts/addons/`
   - **Linux**: `~/.config/blender/<version>/scripts/addons/`
2. Blender を起動（または再起動）
3. **Edit > Preferences > Add-ons** で「Blokus」を検索し、有効化する

### 方法C: テキストエディタから直接実行（開発・テスト用）

1. Blender を起動
2. **Scripting** ワークスペースに切り替える
3. テキストエディタで `blokus_builder.py` を **Open** する
4. **Run Script**（再生ボタン または `Alt+P`）を押す

> この方法ではBlender再起動のたびに再実行が必要です。

---

## 3. UIパネルの場所

1. 3D Viewport 上で **N キー** を押してサイドバーを開く
2. タブ一覧に **「Blokus」** が追加されているのでクリック

パネルは以下のセクションに分かれています:

```
┌─────────────────────────┐
│ Cell & Clearance        │  ← セルサイズ、クリアランス
├─────────────────────────┤
│ Board                   │  ← ボード基板、リブ、フレーム
├─────────────────────────┤
│ Piece                   │  ← ピース厚み、ベベル、溝寸法（自動表示）
├─────────────────────────┤
│ Board Split             │  ← 分割数、ダボ寸法
├─────────────────────────┤
│ Colors                  │  ← 生成する色の ON/OFF
├─────────────────────────┤
│ Generate                │  ← 生成ボタン群
├─────────────────────────┤
│ Export                   │  ← STL出力設定
├─────────────────────────┤
│ Utilities               │  ← クリーン、デバッグ設定
└─────────────────────────┘
```

---

## 4. パラメータ一覧

### 4.1 Cell & Clearance

| パラメータ | 初期値 | 説明 |
|-----------|--------|------|
| Cell Size | 20.0 mm | 1マスの辺の長さ |
| Clearance | 0.20 mm | 片側の遊び（溝幅 = リブ幅 + 2 × Clearance） |

### 4.2 Board（ボード）

| パラメータ | 初期値 | 説明 |
|-----------|--------|------|
| Board Thickness | 1.8 mm | 基板の厚み |
| Rib Width | 1.2 mm | 格子リブの幅 |
| Rib Height | 0.9 mm | 格子リブの高さ（凸の高さ） |
| Frame Width | 8.0 mm | 外周フレーム幅 |

### 4.3 Piece（ピース）

| パラメータ | 初期値 | 説明 |
|-----------|--------|------|
| Piece Thickness | 3.2 mm | ピース全体の厚み |
| Bevel Top | 0.4 mm | 上面の面取り量 |
| Bevel Bottom | 0.2 mm | 下面の面取り量（象足対策） |

パネル内に以下の自動計算値が表示されます:

- **Groove W**: 溝の幅 = `Rib Width + 2 × Clearance`
- **Groove D**: 溝の深さ = `Rib Height + 0.25`
- 残肉が 1.6 mm 未満の場合は警告が表示されます

### 4.4 Board Split（ボード分割）

| パラメータ | 初期値 | 説明 |
|-----------|--------|------|
| Split X | 2 | X方向の分割数 |
| Split Y | 2 | Y方向の分割数 |
| Dowel Diameter | 6.0 mm | ダボの直径 |
| Dowel Length | 4.0 mm | ダボの長さ |
| Dowel Clearance | 0.2 mm | 受け穴側の追加半径 |

> 2×2 分割の場合、10×10 セル（200×200 mm）のタイルが4枚生成されます。

### 4.5 Colors（色）

Red / Blue / Yellow / Green それぞれを ON/OFF できます。
OFF にした色のピースは生成されません（テスト印刷で1色だけ試したいときに便利）。

### 4.6 Generate（生成）

| トグル/パラメータ | 説明 |
|-----------------|------|
| Board | Generate All 時にボードを生成する |
| Pieces | Generate All 時にピースを生成する |
| Layout Gap | ピース間の隙間（印刷プレート整列用） |

### 4.7 Export（出力）

| パラメータ | 初期値 | 説明 |
|-----------|--------|------|
| Export Dir | `//exports` | 出力先（`//` = .blend ファイルの相対パス） |
| Export Mode | Per Piece | 出力単位（後述） |
| Apply Transforms | ON | 回転・スケールを適用してからエクスポート |

---

## 5. 基本的な使い方

### 5.1 ボードとピースを一括生成する

1. パラメータを調整（初期値のままでもOK）
2. **Generate All** ボタンを押す
3. 生成完了を待つ（ピース84個 + ボード4タイルで数分程度）

### 5.2 ボードだけ / ピースだけ生成する

- **Generate Board** : ボードタイルのみ生成
- **Generate Pieces** : ピースのみ生成

### 5.3 パラメータを変えて再生成する

パラメータを変更して再度 Generate ボタンを押すだけです。
既存の生成物は自動的に削除されてから再生成されます（差分更新ではなく毎回フル再生成）。

### 5.4 STL をエクスポートする

1. **Export Dir** を設定（デフォルトは .blend ファイルと同じ場所の `exports/`）
2. **Export Mode** を選択
3. **Export STL** ボタンを押す

> エクスポートの前に `.blend` ファイルを一度保存してください。
> `//` 相対パスは保存されていないファイルでは解決できません。

### 5.5 生成物をすべて削除する

**Clean All** ボタンを押すと、すべての Blokus 関連オブジェクトとコレクションが削除されます。

---

## 6. STL エクスポートモード

| モード | 出力先 | 内容 |
|--------|--------|------|
| **Per Piece** | `exports/pieces/red/BLK_P_RED_I1.stl` 等 | ピース1個ずつ個別STL + ボードタイル |
| **Per Color** | `exports/pieces/red.stl` 等 | 色ごとに全ピース結合した1つのSTL + ボードタイル |
| **Board Tiles** | `exports/board/BLK_B_0_0.stl` 等 | ボードタイルのみ |

Per Piece / Per Color モードでは、ボードタイルも同時にエクスポートされます。

---

## 7. コレクション構成

生成されるオブジェクトは以下のコレクションに整理されます:

| コレクション | 内容 |
|-------------|------|
| `BLK_BOARD` | ボードタイル（`BLK_B_0_0`, `BLK_B_1_0`, ...） |
| `BLK_PIECES_RED` | 赤ピース 21個 |
| `BLK_PIECES_BLUE` | 青ピース 21個 |
| `BLK_PIECES_YELLOW` | 黄ピース 21個 |
| `BLK_PIECES_GREEN` | 緑ピース 21個 |
| `BLK_TMP` | Boolean中間オブジェクト（Keep Cutters ON時のみ） |

---

## 8. オブジェクト命名規則

| 種別 | 命名パターン | 例 |
|------|-------------|-----|
| ピース | `BLK_P_{色}_{形状名}` | `BLK_P_RED_T5` |
| ボードタイル | `BLK_B_{X}_{Y}` | `BLK_B_0_1` |

各オブジェクトには以下のカスタムプロパティが付与されます:

- `blk_cell`: 生成時のセルサイズ
- `blk_clear`: 生成時のクリアランス
- `blk_piece_name` / `blk_color`: ピース名・色（ピースのみ）
- `blk_tile_x` / `blk_tile_y`: タイル座標（ボードのみ）

---

## 9. 嵌合の調整ワークフロー

ピースのハマり具合は主に **Clearance** パラメータで調整します。

| 状況 | 対処 |
|------|------|
| きつくて入らない | Clearance を大きくする（例: 0.20 → 0.25） |
| ガタつく・ゆるい | Clearance を小さくする（例: 0.20 → 0.15） |
| 溝が浅すぎてハマらない | Rib Height を上げるか、Piece Thickness を上げる |

**推奨手順:**

1. まず1色分だけ生成（Colors で1色だけON）
2. 代表的なピース2〜3個とボード1タイルを印刷
3. 嵌合を確認して Clearance を調整
4. 満足したら全色 Generate All → Export STL

---

## 10. 印刷のヒント

### ボードタイル

- 薄いパーツなので**ブリムを付ける**ことを推奨
- 裏面に反り防止の補強リブが自動生成されます
- タイル間はダボ（凸）と受け穴（凹）で接合する設計です
  - 別途接着剤や輪ゴム等で固定してもOK

### ピース

- 溝が下面に来る向き（上面が平ら）でそのまま印刷できます
- **ラフトは不要**（ベベル底面が象足を逃がす設計）
- 色ごとにフィラメントを変えて印刷してください

---

## 11. トラブルシューティング

### パネルが表示されない

- アドオンが有効になっているか確認（Edit > Preferences > Add-ons）
- 3D Viewport で **N キー** を押してサイドバーを開き、「Blokus」タブを探す

### Generate でエラーが出る

- エラーメッセージは Blender 下部のステータスバーに表示されます
- よくあるエラー:
  - `Remaining wall < 1.6mm`: Piece Thickness を上げるか Rib Height を下げる
  - `Clearance is large`: Clearance が 0.35mm を超えている（警告のみ、生成は続行）

### Boolean が失敗する

- まれに Boolean 演算が失敗することがあります
- EXACT ソルバーが失敗した場合、自動的に FAST ソルバーにフォールバックします
- それでも失敗する場合は Cell Size を微調整（例: 20.0 → 20.01）してリトライしてください

### Export STL でエラーが出る

- `.blend` ファイルが保存されていることを確認してください
- Export Dir が `//exports`（デフォルト）の場合、.blend ファイルの保存先が基準になります
- 絶対パスを指定することもできます（例: `/home/user/blokus_stl/`）

---

## 12. ファイル構成

```
blocks_blender/
├── blokus_builder.py              # アドオン本体（単一ファイル）
└── docs/
    ├── reverse_groove_design.md   # 設計書
    └── usage_guide.md             # このドキュメント
```
