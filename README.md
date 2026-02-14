## Siril Preprocessing Flow GUI / Siril 前処理フロー GUI

### Overview / 概要

This repository provides a GUI to build and execute preprocessing scripts for the astrophotography software **Siril**.  
It helps you configure **conversion, calibration, registration, and stacking** steps, then generates the corresponding Siril script and can run it.

このリポジトリは、天体画像処理ソフト **Siril** 用の前処理スクリプトを作成・実行するための **GUI** を提供します。  
**コンバート、キャリブレーション、位置合わせ（レジストレーション）、スタッキング** を GUI で設定し、対応する Siril スクリプトを生成して実行できます。

---

### Features / 主な機能

- **Automated Workflow**
  - Traditionally, GUI operations required manual execution of each step (Convert, Calibration, Registration, Stack).
  - Even with automated scripts, users often had to manually edit the script code.
  - **Single-Click Execution:** This tool enables fully automated execution of the entire workflow via an intuitive GUI.

- **一連の流れを自動化**
  - 従来の GUI 操作では、Convert, Calibration, Registration, Stack をそれぞれ手動で実行する必要がありました。
  - スクリプトで自動化する場合でも、従来はコードを直接書き換える手間がありました。
  - **GUI で完結:** 本ツールは、GUI 操作だけでこれらの一連の工程をすべて自動実行できます。

- **Support for Full Preprocessing Flow**
  - GUI tabs for **Convert**, **Calibration**, **Registration**, and **Stacking**.
  - Automatic master frame creation (Bias, Dark, Flat).
  - Advanced options: Drizzle, image rejection filters, and quality-based weighting.

- **前処理工程をフルサポート**
  - **Convert / Calibration / Registration / Stacking** 用の専用タブ。
  - マスターフレーム（Bias, Dark, Flat）の自動生成。
  - ドリズル対応、リジェクトアルゴリズム、品質ベースの重み付けなど高度な設定も可能。

---

### Requirements / 必要環境

- Siril v1.4.0 or later

---

### Directory structure / 想定ディレクトリ構成

The script assumes the following structure relative to where you run it:

- `biases/` – bias frames  
- `flats/` – flat frames  
- `darks/` – dark frames  
- `lights/` – light frames  
- `process/` – (usually `../process` from each subfolder) temporary converted sequences  
- `masters/` – (usually `../masters`) output master frames  

スクリプトは、実行ディレクトリから見て次のような構成を想定しています:

- `biases/` – バイアスフレーム  
- `flats/` – フラットフレーム  
- `darks/` – ダークフレーム  
- `lights/` – ライトフレーム  
- `process/` – （各サブフォルダから見て `../process`）コンバート後のシーケンス用  
- `masters/` – （`../masters`）マスターフレームの出力先  

You can adjust the exact paths via the GUI fields if your layout is different.

レイアウトが異なる場合でも、GUI 上の各入力欄からパスを変更できます。

---

### How to run / 使い方

#### English
1. **Launch Siril**.
2. Run the script by selecting **`Siril-prepflow.py`** from Siril's menu. 
3. Configure each tab (**Convert**, **Calibration**, **Registration**, **Stacking**) according to your dataset and preferences.
4. Click **“Generate Script”** to create the Siril script; it will appear in the text area.
5. Click **“Run Script in Siril”** to execute the script step‑by‑step.

#### 日本語
1. **Siril を起動**します。
2. Siril のメニューから **`Siril-prepflow.py`** を選択して実行します。
3. データセットに合わせて、各タブ（**Convert / Calibration / Registration / Stacking**）の設定を行います。
4. **「Generate Script」** ボタンを押すと、Siril スクリプトが生成され、テキストエリアに表示されます。
5. **「Run Script in Siril」** ボタンを押すと、生成されたスクリプトが Siril で実行されます。

---

### Notes / 注意事項

- The GUI can still be used to **generate scripts** even if the connection to Siril fails; in that case, you can copy the script and run it manually inside Siril.
- Drizzle requires **non‑debayered** data; the GUI automatically disables debayering options when drizzle is enabled (and vice versa).
- Some advanced Siril options (e.g., distortion from file/masters) are partially wired and may need manual script editing depending on your workflow.

- Siril への接続に失敗しても、GUI 自体は **スクリプト生成ツール** として利用できます。その場合は生成されたスクリプトをコピーし、Siril 内で手動実行してください。
- ドリズルは **デベイヤー前の生データ** を必要とするため、ドリズル有効時には GUI 側でデベイヤー設定を自動的に無効化します（その逆も同様）。  
- 一部の高度な Siril オプション（例: 歪曲補正ファイルの扱いなど）は GUI からは簡略化されており、必要に応じて生成スクリプトを手動で調整してください。


