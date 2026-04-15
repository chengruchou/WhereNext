# MG-DSGAT
This repository provides a PyTorch implementation of the Multi-granularity User Intent and Dual-channel Sparse Attention Network, a model designed for sequential recommendation and user behavior modeling.

# SBR POI Recommendation System

本專案實作一個「下一個地點推薦（Next POI Recommendation）」系統。

目標是根據使用者目前的地點序列，預測下一個可能前往的地點。

---

# Project Overview

本系統使用 Session-Based Recommendation（SBR）模型。

簡單理解：

輸入：
使用者已去過的地點序列  
例如：[A -> B -> C]

輸出：
預測下一個地點（例如 D）

---

# Repository Structure

src/
- infer_sbr.py：推論（inference）主程式
- build_gowalla_dataset.py：建立資料集與 mapping
- model_exp30.py：模型架構
- trainer.py：訓練流程
- utils.py：資料處理

datasets/
- Gowalla/：模型使用資料與 mapping

save_model/
- 存放已訓練好的模型

---

# Dataset 概念

## raw_location_id vs item_id

raw_location_id：
原始資料中的地點 ID（不連續）

item_id：
模型內部使用的 ID（連續）

模型只使用 item_id。

---

## mapping

模型需要透過 mapping 轉換：

raw_location_id -> item_id

使用：
- raw_location2item.json
- item2raw_location.json

---

# Dataset 檔案說明

train.txt  
模型訓練資料（prefix -> target）

test.txt  
模型測試資料

all_train_seq.txt  
完整訓練路徑

raw_location2item.json  
raw id -> item_id

item2raw_location.json  
item_id -> raw id

poi_metadata.json  
地點資訊（座標、類別等）

build_manifest.json  
資料集設定與統計資訊

---

# 如何做 Inference


## Step 1：準備輸入檔案

建立 test.txt（raw 格式）：

[user_id] timestamp latitude longitude location_id  
196514 2010-07-24T13:45:06Z 53.3648 -2.2723 145064  
196514 2010-07-24T13:44:58Z 53.3605 -2.2763 1275991  
196514 2010-07-24T13:44:46Z 53.3653 -2.2754 376497  

注意：
- 必須包含 location_id
- timestamp 會用來排序

---

## Step 2：執行 inference（支援三種輸入方式）

### 方法 1：直接輸入 internal item_id

python .\src\infer_sbr.py --dataset Gowalla --checkpoint save_model\Demo_model_exp30_Gowalla_512_seed_2023-last_k_4_best_model.pt --session 12,45,91,203 --topk 10

說明：
- `--session` 為逗號分隔的數字
- 這些數字是 **item_id（已經 mapping 過的 ID）**
- 不需要 mapping 檔案

---

### 方法 2：從檔案讀取 internal item_id

python .\src\infer_sbr.py --dataset Gowalla --checkpoint save_model\Demo_model_exp30_Gowalla_512_seed_2023-last_k_4_best_model.pt --session_file session.txt --topk 10

session.txt 範例內容：

12 45 91 203

說明：
- 檔案內為一串 item_id
- 同樣是 **已 mapping 過的 ID**
- 不需要 mapping 檔案

---

### 方法 3：使用 raw Gowalla 路徑（建議）

python .\src\infer_sbr.py --dataset Gowalla --checkpoint save_model\Demo_model_exp30_Gowalla_512_seed_2023-last_k_4_best_model.pt --gowalla_visit_file test.txt --mapping_json datasets\Gowalla\raw_location2item.json --reverse_mapping_json datasets\Gowalla\item2raw_location.json --topk 10 --output_json out.json

說明：
- 輸入為 raw dataset 格式（location_id 為原始 ID）
- 會透過 mapping 自動轉成 item_id
- 這是最接近實際應用的方式

---

## 補充說明

- 模型實際只使用 item_id 進行計算
- raw_location_id 需要透過 mapping 轉換
- item_id 是由訓練資料產生的連續編號
- raw_location_id 是原始資料中的 ID（不連續）

## Step 3：查看結果

輸出：
out.json

包含：
- 預測結果（Top-K 地點）
- 對應的 raw_location_id

---

# Inference 流程

raw data（location_id）  
-> mapping（轉 item_id）  
-> 模型預測  
-> item_id  
-> reverse mapping  
-> raw_location_id  

---

# 注意事項

## 1. train.txt / test.txt 不是文字檔

這些檔案實際是 pickle（二進位），不是純文字。

不能用記事本打開，看到亂碼是正常的。

如果要查看：

import pickle  
with open("datasets/Gowalla/train.txt", "rb") as f:  
    data = pickle.load(f)  

---

## 2. mapping 必須對應模型

mapping 改變但使用舊模型，結果會錯。

---

## 3. 模型不吃 raw id

一定要先轉成 item_id。

---

## 4. 有些 POI 沒有 item_id

代表模型沒有學過，無法直接使用。

