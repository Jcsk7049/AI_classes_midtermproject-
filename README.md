# 🍎🍌🍊🍉 水果影像分類 — KNN & SVM 機器學習專題

> **Fruit Image Classification using K-Nearest Neighbors & Support Vector Machine**  
> AI 課程期中專題 | Python + scikit-learn

---

## 專題目標

以**監督式學習**方式，使用 **KNN** 與 **SVM** 兩種演算法，訓練能辨識四種水果的模型，並支援非水果影像「無此項目」偵測。

| 類別 | 水果 | 訓練影像數 |
|:----:|------|:---------:|
| 0 | 🍎 Apple (蘋果) | 80 張 |
| 1 | 🍌 Banana (香蕉) | 80 張 |
| 2 | 🍊 Orange (柳橙) | 80 張 |
| 3 | 🍉 Watermelon (西瓜) | 80 張 |

---

## 📁 檔案說明

| 檔案 | 說明 |
|------|------|
| `fruit_classification_colab.ipynb` | 主要訓練 Notebook（完整流程） |
| `fruit_predictor.py` | [積分題] 獨立預測腳本 |
| `requirements.txt` | 所需 Python 套件 |

---

## 一、訓練集資料樣本

> 資料集來源：[Fruits-360](https://github.com/Horea94/Fruit-Images-Dataset) — 100×100 像素，每類 80 張訓練影像

![訓練集樣本圖](sample_images.png)

---

## 二、特徵工程視覺化

> 結合 **HOG**（形狀/紋理）+ **RGB/HSV 顏色直方圖** 作為特徵輸入

![特徵視覺化](feature_visualisation.png)

**特徵組成：**

| 特徵 | 維度 | 說明 |
|------|:----:|------|
| HOG | ~1764 | 描述形狀輪廓與紋理方向 |
| RGB 顏色直方圖 | 96 | 各通道 32 bins，正規化 |
| HSV 顏色直方圖 | 50 | Hue 18 + Saturation 32，正規化 |

---

## 三、類別分布

![類別分布](class_distribution.png)

---

## 四、KNN 訓練過程

> 使用 **5-fold 交叉驗證**，測試 K = 1 ~ 30，自動選出最佳 K 值

![KNN K值選擇曲線](knn_k_selection.png)

- **左圖**：K 值 vs CV 準確率（藍色帶為 ±1 標準差）
- **右圖**：訓練集 vs 驗證集準確率對比（可觀察過擬合情況）
- 紅色虛線標示最佳 K 值

---

## 五、SVM 訓練過程

> 對 **Linear** 與 **RBF** 兩種核函數進行 **GridSearchCV** 超參數搜索

![SVM Grid Search 結果](svm_gridsearch.png)

- **左圖**：Linear SVM — 不同 C 值對應準確率（含誤差條）
- **右圖**：RBF SVM — C × Gamma 組合熱力圖（顏色越深準確率越高）

---

## 六、訓練曲線（Learning Curves）

> 展示兩模型隨訓練樣本增加的表現變化，判斷過擬合/欠擬合

![訓練曲線](learning_curves.png)

- 綠色：訓練集準確率
- 紅色：驗證集準確率
- 兩線收斂 → 模型泛化良好

---

## 七、最終評估結果

### KNN 混淆矩陣

![KNN 混淆矩陣](knn_confusion_matrix.png)

> 左：原始計數　右：正規化（各行百分比）

### SVM 混淆矩陣

![SVM 混淆矩陣](svm_confusion_matrix.png)

> 左：原始計數　右：正規化（各行百分比）

### Accuracy / Precision / F1 比較

![模型比較](model_comparison.png)

> 左：KNN vs SVM 各指標分組長條圖　右：摘要比較表（標示較佳模型）

---

## 八、[積分題] 獨立載入模型預測

> 訓練完成後，不依賴訓練變數，直接從磁碟載入 `.pkl` 模型辨識新影像

![積分題預測展示](bonus_prediction_demo.png)

> 每欄：上方為輸入影像，下方為各類別預測機率長條圖，紅色為最高預測類別

**命令列使用方式：**
```bash
python fruit_predictor.py --image apple.jpg --model svm
python fruit_predictor.py --image banana.jpg --model knn
python fruit_predictor.py --image cat.jpg --model svm   # → ❓ 無此項目
```

---

## 九、[進階] 無此項目偵測（OOD Detection）

> 當輸入影像不屬於任何已知水果類別時（如貓、車子等），模型輸出「無此項目」

![OOD偵測展示](ood_detection_demo.png)

> 三種非水果合成影像：所有類別機率均低於紅色虛線門檻（52%），正確回傳「無此項目」

**運作原理：**
```
輸入影像 → 提取 HOG + 顏色特徵 → 計算各類別機率
  ├─ 最高機率 ≥ 52%  → 輸出對應水果 🍎 🍌 🍊 🍉
  └─ 最高機率 < 52%  → 輸出「❓ 無此項目」
```

---

## 技術架構

```
資料集 Fruits-360（每類 80 張，共 320 張訓練 / 140 張測試）
        ↓
特徵提取: HOG + RGB/HSV 顏色直方圖（約 1910 維）
        ↓
 StandardScaler 正規化
        ↓
   ┌────┴────┐
  KNN       SVM
(5-fold CV)  (GridSearchCV)
(最佳 K 值)  (Linear / RBF)
   └────┬────┘
     評估比較
  Accuracy / Precision / F1
        ↓
   儲存模型（saved_models/*.pkl）
        ↓
  獨立預測 + OOD 偵測（無此項目）
```
