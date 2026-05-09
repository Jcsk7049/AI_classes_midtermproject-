# 🍎🍌🍊 水果影像分類 — KNN & SVM 機器學習專題

> Fruit Image Classification using K-Nearest Neighbors & Support Vector Machine  
> AI 課程期中專題 | Google Colab / GCP

---

## 專題目標

以**監督式學習**方式，使用 **KNN** 與 **SVM** 兩種演算法，訓練能辨識三種水果的模型：

| 類別 | 水果 | 訓練影像數 |
|------|------|-----------|
| 0 | 🍎 Apple (蘋果) | ≥ 60 張 |
| 1 | 🍌 Banana (香蕉) | ≥ 60 張 |
| 2 | 🍊 Orange (柳橙) | ≥ 60 張 |

資料集來源：[Fruits-360](https://github.com/Horea94/Fruit-Images-Dataset)（100×100 像素）

---

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `fruit_classification_colab.ipynb` | **主要 Colab Notebook** — 完整訓練流程 |
| `fruit_predictor.py` | **[積分題]** 獨立預測腳本，載入已訓練模型辨識水果 |
| `requirements.txt` | 所需 Python 套件 |

---

## 快速開始

### 1. 在 Google Colab 執行

1. 上傳 `fruit_classification_colab.ipynb` 至 [Google Colab](https://colab.research.google.com/)
2. 依序執行所有儲存格（Runtime → Run all）
3. 資料集會自動從 GitHub 下載，無需 API 金鑰

### 2. 本地執行

```bash
pip install -r requirements.txt
jupyter notebook fruit_classification_colab.ipynb
```

---

## Notebook 結構

| 節次 | 內容 |
|------|------|
| 第一節 | 環境設定 — 安裝套件、匯入函式庫 |
| 第二節 | 資料集下載 — git sparse-checkout / Kaggle 備用 |
| 第三節 | 資料載入與探索 — 樣本圖、類別分布 |
| 第四節 | 特徵工程 — HOG + RGB/HSV 顏色直方圖 |
| 第五節 | **KNN 訓練** — K 值 5-fold CV、訓練曲線、混淆矩陣 |
| 第六節 | **SVM 訓練** — GridSearchCV、熱力圖、混淆矩陣 |
| 第七節 | 訓練曲線 (Learning Curves) |
| 第八節 | 模型比較 — Accuracy / Precision / F1 |
| 第九節 | 儲存模型 (`saved_models/`) |
| 第十節 | **[積分題]** 載入模型 + 自訂影像辨識 |

---

## [積分題] 獨立預測

訓練完成後，使用 `fruit_predictor.py` 辨識任意水果影像：

```bash
# 使用 SVM 模型
python fruit_predictor.py --image path/to/apple.jpg --model svm

# 使用 KNN 模型
python fruit_predictor.py --image path/to/banana.jpg --model knn

# 指定模型目錄
python fruit_predictor.py --image orange.jpg --model svm --models_dir ./saved_models
```

---

## 評估指標說明

- **Accuracy** — 整體分類正確率
- **Precision** (weighted) — 各類別精確率的加權平均
- **Recall** (weighted) — 各類別召回率的加權平均
- **F1 Score** (weighted) — Precision 與 Recall 的調和平均數

---

## 技術架構

```
特徵提取 (Feature Extraction)
  ├── HOG (Histogram of Oriented Gradients) — 形狀/紋理
  ├── RGB 顏色直方圖 (32 bins × 3 ch = 96 維)
  └── HSV 顏色直方圖 (Hue 18 + Sat 32 = 50 維)
         ↓
StandardScaler 正規化
         ↓
    ┌────┴────┐
   KNN       SVM
  (最佳K)  (GridSearch)
    └────┬────┘
      評估比較
```
