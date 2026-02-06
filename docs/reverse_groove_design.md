# Blokus互換 逆溝方式 設計書

Blokus互換（"ルール/仕組み同等・サイズ感ほぼ同等"）の **逆溝方式**（ボード＝凸リブ、ピース裏＝凹溝）を、**UIパネル + Python再生成**で実現するための設計書。
CodeX にそのまま実装させられる粒度で、データ構造・UI・生成アルゴリズム・エクスポート・検証・タスク分解まで落としている。

---

## 1. 目的・スコープ

### 1.1 目的

* Blender上でパラメータ（mm）をUIから調整し、**ボード/ピースを再生成**して、**STL出力**できるツールを作る。
* "本家と完全一致"は不要。重要なのは：

  * **ピースの種類/個数（21形状×4色）**
  * **20×20ボード**
  * **ボードに気持ちよくハマる逆溝機構**
  * **ボードは材料費を抑えるため薄く**（ただし反り対策あり）

### 1.2 対象環境

* Blender **3.6 LTS以上**（推奨：4.x）
* FDM 0.4mmノズル前提の初期値（ただしUIで調整可能）

### 1.3 非スコープ（初版ではやらない）

* ルール説明UI、ゲーム進行支援
* 色替えの自動スライサ連携
* 高速パッキング最適化（簡易棚詰めで十分）

---

## 2. ユーザー体験（UX）

### 2.1 UI（Nパネル）

* 3D Viewport > Sidebar（Nキー） > 「Blokus」タブ
* パラメータ（セルサイズ、リブ寸法、クリアランス、分割数等）を調整
* ボタン：

  * **Generate Board**
  * **Generate Pieces**
  * **Generate All**
  * **Export STL**
  * **Clean**

### 2.2 再生成の原則

* "差分更新"はしない。
  **毎回「該当コレクションを消して作り直す」**（確実性優先）
* 生成物はコレクションで分離：

  * `BLK_BOARD`
  * `BLK_PIECES`
  * `BLK_CUTTERS`（必要なら、デバッグ時のみ残す）

---

## 3. パラメータ仕様（Scene Properties）

`bpy.types.Scene.blk_params` に `PropertyGroup` をぶら下げる。

### 3.1 寸法（mm）

推奨初期値（安全寄り・後でUI調整）：

* `cell` = 20.0
* `clear` = 0.20  （片側クリアランス）
* ボード

  * `board_t` = 1.8（基板）
  * `rib_w` = 1.2（格子リブ幅）
  * `rib_h` = 0.9（格子リブ高）
  * `frame_w` = 8.0（外周フレーム幅）
* ピース

  * `piece_t` = 3.2
  * `groove_w` = `rib_w + 2*clear`（自動計算 or ユーザー指定）
  * `groove_d` = `rib_h + 0.25`（自動計算 or ユーザー指定）
  * `bevel_top` = 0.4
  * `bevel_bottom` = 0.2（下側の逃げ、象足対策）
* 分割

  * `split_x` = 2 / `split_y` = 2（2×2推奨）
  * `dowel_d` = 6.0 / `dowel_len` = 4.0 / `dowel_clear` = 0.2
* 出力

  * `export_dir`（blend相対 `//exports` をデフォルト）
  * `export_mode`（per_piece / per_color / board_tiles）
  * `apply_transforms`（True推奨）

### 3.2 ルール系

* `colors_enabled`：4色（red/blue/yellow/green）On/Off
* `make_board` / `make_pieces`：Generate All用

---

## 4. データ定義（ピース形状）

### 4.1 形状表現

* 21形状は **セル座標の集合**で表す（整数格子）。
* 例：`[(0,0),(1,0),(0,1)]`

```python
PIECES = {
  "I1": [(0,0)],
  "I2": [(0,0),(1,0)],
  ...
  # 合計21
}
```

### 4.2 検証用の不変条件

* 1色の総セル数：**89**
* 個数内訳：

  * 1マス×1
  * 2マス×1
  * 3マス×2
  * 4マス×5
  * 5マス×12

※ 初期実装では `validate_pieces()` で上記をチェックし、NGならUIにエラー表示して生成を止める。

---

## 5. 生成アルゴリズム設計

### 5.1 共通ユーティリティ

* `ensure_scene_units_mm()`

  * `scene.unit_settings.system = 'METRIC'`
  * `scene.unit_settings.scale_length = 0.001`（= 1 unit = 1mm）
  * ただしBlender内部単位運用に慣れているなら「unitは触らず mm換算で生成」でもOK。初版は **mmで統一**を推奨。

* `get_or_create_collection(name)`

* `wipe_collection(name)`（オブジェクト削除＋コレクション掃除）

* `set_active(obj)`, `select_only(obj)`

---

### 5.2 ボード生成（逆溝の"凸"側）

#### 5.2.1 形状

* **基板**：`(20*cell + 2*frame_w)` 正方形、厚み `board_t`
* **格子リブ**：

  * 縦リブ：21本（x = 0..20の境界線）
  * 横リブ：21本（y = 0..20）
  * 幅 `rib_w`、高さ `rib_h`
* **外周フレーム**：基板上に一段高い枠（任意。剛性と持ちやすさ）

#### 5.2.2 実装方式

* `bpy.ops.mesh.primitive_cube_add` を使って直方体を量産
* 最後に `bpy.ops.object.join` で一体化（またはコレクション内に分割のままでも可）
* 材料費を抑える＆反り防止で、裏面補強リブは「別オブジェクトでunion」か「join」で良い（Booleanは避ける）

#### 5.2.3 分割（重要）

ボードは一体で印刷できない前提：

* `split_x × split_y` に分割して **タイル単位**で生成
* 例：2×2なら 10×10セル/タイル
* タイル境界には **ダボ/受け穴**を生成（裏面推奨）

  * 受け穴は `dowel_clear` 分だけ大きくする

---

### 5.3 ピース生成（逆溝の"凹"側）

#### 5.3.1 ピース外形（セル集合 → 2D輪郭）

方法：**セルの辺集合から外周抽出**（確実・実装容易）

1. 各セルの4辺を「無向エッジ」として列挙
2. 共有辺（同じ辺が2回出る）を削除
3. 残った辺が外周
4. 外周辺を辿って頂点ループ（ポリライン）を復元
5. 2D面を作成 → 押し出し `piece_t`

※ ここは `bmesh` で2D面を作るのが実装しやすい。

#### 5.3.2 逆溝（裏面の溝）生成：設計方針

目的：ボードの凸リブに噛む溝をピース裏に掘る。

**溝線の定義（推奨）**

* ピースが覆うセル範囲に存在する「格子線」に沿って溝を入れる
* "本家っぽいハマり"優先なら **内部格子線 + 外周格子線**の両方に溝を入れる
  （外周溝なしだと端の噛みが弱くなる）

#### 5.3.3 溝カッター生成（Boolean差分）

最も堅い実装：

1. `make_groove_bars(piece_bbox, grid_lines)`

   * 溝用の細長い直方体（バー）を作る
   * 幅 `groove_w`、高さ `groove_d`
   * Z位置はピース下面に合わせる（下面から上方向に掘る）
2. バー群を `join`（1オブジェクトに統合）
3. **トリミング（重要）**

   * バーがピース外形からはみ出すので、
     `INTERSECT(バー, ピース)` を作って "ピース内部だけのバー" にする
4. `DIFFERENCE(ピース, トリム済みバー)` で溝を掘る
5. 下面の象足逃げ（`bevel_bottom`）を別途付ける（Bevel modifierを下面だけに掛けるのが難しければ、下面エッジに小面取りを入れる簡易処理でOK）

**Booleanの安定化設定（推奨）**

* Solver：EXACT
* 自己交差対策：バー同士が重なる箇所が多いので、先にjoinしておく
* 失敗時は `apply_scale` を徹底

> パフォーマンスは落ちるが、21×4=84個でも現実的（数分以内）に収まる設計。

#### 5.3.4 仕上げ

* 上面エッジに `bevel_top`（軽い面取り）
* 法線再計算（`mesh.normals_split_custom_set` は不要、単に `bpy.ops.mesh.normals_make_consistent` で可）
* 原点：ピース中心 or 左下基準。STL管理しやすい基準で統一。

---

## 6. 配置（プレート整列）

* `layout_mode = shelf`（棚詰め）
* `gap_xy = 2.0mm`（印刷中の熱干渉や剥がしやすさ）
* `per_color_plate`（色ごとに別コレクション・別配置も可能）
* 大きいピース順に並べる（外接矩形面積の降順）

---

## 7. STLエクスポート設計

### 7.1 Exportモード

* `per_piece`：`exports/pieces/red/I1.stl`
* `per_color`：色ごとにjoinして `exports/pieces/red.stl`
* `board_tiles`：タイル単位 `exports/board/board_0_0.stl`

### 7.2 実装要点

* `bpy.ops.export_mesh.stl(filepath=..., use_selection=True)`
* ループ内で `select_only(obj)` を徹底
* `apply_transforms=True` なら `bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)`
* 出力先は `//` 相対＋フォルダ自動作成

---

## 8. バリデーション・エラーハンドリング

### 8.1 バリデーション

* `validate_pieces()`：

  * 総セル数=89
  * 連結性（BFSで1成分）
  * セル重複なし
* `validate_params()`：

  * `groove_w > rib_w`
  * `piece_t - groove_d >= 1.6`（残肉）
  * `clear >= 0`、過大でガタつく範囲も警告（例：0.35以上）

### 8.2 UIへのフィードバック

* Operator の `self.report({'ERROR'}, msg)` で表示
* 生成に失敗した場合は中間オブジェクトをクリーンアップして終了

---

## 9. 実装タスク分解（CodeX向け）

### Phase 0：骨格（アドオン化）

- [ ] `blokus_builder.py`（単一ファイル）
- [ ] `PropertyGroup`（パラメータ定義）
- [ ] `Panel`（UI描画）
- [ ] Operators（Generate/Export/Clean）

### Phase 1：ピース定義と検証

- [ ] `PIECES` 21形状の確定（セル座標）
- [ ] `validate_pieces()` 実装

### Phase 2：ピース外形生成

- [ ] セル→外周抽出（辺の重複削除→ループ復元）
- [ ] 2D面→押し出し→メッシュ化
- [ ] 上面bevel

### Phase 3：逆溝（裏溝）Boolean

- [ ] 溝バー生成（X/Y格子線）
- [ ] バーのINTERSECTトリム
- [ ] ピースへのDIFFERENCE適用
- [ ] 失敗時の再試行（apply_scaleして再Boolean）

### Phase 4：ボード生成（分割＋ダボ）

- [ ] タイル生成（基板＋格子リブ＋フレーム）
- [ ] 裏補強リブ（反り対策）
- [ ] ダボ/受け穴（タイル間）

### Phase 5：配置・出力

- [ ] 棚詰め配置
- [ ] STL export（3モード）

### Phase 6：仕上げ

- [ ] 生成物の命名規則・コレクション管理の堅牢化
- [ ] デバッグオプション（カッターを残す等）

---

## 10. 命名規則・コレクション設計

* コレクション

  * `BLK_BOARD`
  * `BLK_PIECES_RED` / `..._BLUE` / `..._YELLOW` / `..._GREEN`
  * `BLK_TMP`（Boolean中間）
* オブジェクト名

  * `BLK_P_{color}_{pieceName}`
  * `BLK_B_{tileX}_{tileY}`
* カスタムプロパティ

  * 生成時のパラメータスナップショットを `obj["blk_cell"]=...` のように付与（後で「このSTLはどの設定で作った？」が追える）

---

## 11. 受け入れ基準（Done定義）

* UIから `cell/clear/rib_w/rib_h/piece_t/groove_*` を変えて **再生成**できる
* `Generate All` で

  * ボード（タイル）生成
  * 4色×21ピース生成
  * プレート上に整列配置
* `Export STL` でモード通りにSTLが生成される
* ピース検証（89セル/色、連結性）にパスする
* 代表パラメータで "はまる/きつい/ガタつく" を `clear` 調整で追い込める（設計として調整ノブが効く）
