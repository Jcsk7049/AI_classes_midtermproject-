"""
[積分題] 獨立水果分類預測器 — 含「無此項目」偵測
Standalone Fruit Classifier with Out-of-Distribution (OOD) detection.

若影像不屬於任何已知水果類別（如貓、車子等），輸出「無此項目」。

Usage:
    python fruit_predictor.py --image apple.jpg
    python fruit_predictor.py --image cat.jpg --model knn
    python fruit_predictor.py --image watermelon.jpg --model svm --threshold 0.52
    python fruit_predictor.py --image unknown.jpg --models_dir ./saved_models
"""

import argparse
import os
import sys
import json
import numpy as np


EMOJI_MAP = {"apple": "🍎", "banana": "🍌", "orange": "🍊", "watermelon": "🍉"}
UNKNOWN   = "無此項目"
DEFAULT_THRESHOLD = 0.52   # max confidence below this → Unknown


def load_dependencies():
    try:
        import cv2
        import joblib
        from skimage.feature import hog
        from PIL import Image
        import matplotlib.pyplot as plt
        return cv2, joblib, hog, Image, plt
    except ImportError as e:
        print(f"❌ 缺少必要套件: {e}")
        print("請執行: pip install opencv-python-headless scikit-image joblib Pillow matplotlib")
        sys.exit(1)


def extract_features(img, cv2, hog_fn):
    """提取 HOG + RGB/HSV 顏色直方圖特徵 (與訓練時完全相同)"""
    img = cv2.resize(img, (64, 64))

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    hog_feat = hog_fn(
        gray, orientations=9, pixels_per_cell=(8, 8),
        cells_per_block=(2, 2), visualize=False, feature_vector=True
    )
    hist_r = np.histogram(img[:, :, 0], bins=32, range=(0, 256))[0]
    hist_g = np.histogram(img[:, :, 1], bins=32, range=(0, 256))[0]
    hist_b = np.histogram(img[:, :, 2], bins=32, range=(0, 256))[0]
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    hist_h = np.histogram(hsv[:, :, 0], bins=18, range=(0, 180))[0]
    hist_s = np.histogram(hsv[:, :, 1], bins=32, range=(0, 256))[0]

    color_rgb = np.concatenate([hist_r, hist_g, hist_b]).astype(float)
    color_rgb /= color_rgb.sum() + 1e-7
    color_hsv = np.concatenate([hist_h, hist_s]).astype(float)
    color_hsv /= color_hsv.sum() + 1e-7
    return np.concatenate([hog_feat, color_rgb, color_hsv])


def load_image(image_path, cv2, Image):
    """載入影像，支援 JPG/PNG"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"找不到影像檔案: {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        img = np.array(Image.open(image_path).convert("RGB"))
    else:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def predict(image_path, model_type="svm", models_dir="./saved_models",
            threshold=DEFAULT_THRESHOLD):
    cv2, joblib, hog_fn, Image, plt = load_dependencies()

    # Load metadata
    meta_path = os.path.join(models_dir, "model_metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            metadata = json.load(f)
        fruit_labels = metadata["fruit_labels"]
    else:
        fruit_labels = ["apple", "banana", "orange", "watermelon"]

    # Load model and scaler
    model_path  = os.path.join(models_dir, f"{model_type}_fruit_classifier.pkl")
    scaler_path = os.path.join(models_dir, "feature_scaler.pkl")

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"找不到模型檔案: {model_path}\n"
            "請先執行 fruit_classification_colab.ipynb 完成訓練並儲存模型。"
        )
    if not os.path.exists(scaler_path):
        raise FileNotFoundError(f"找不到縮放器: {scaler_path}")

    model  = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    print(f"✅ 模型載入成功: {os.path.basename(model_path)}")
    print(f"   信心度門檻: {threshold:.0%}  (低於此值 → {UNKNOWN})")

    # Process image
    img        = load_image(image_path, cv2, Image)
    img_64     = cv2.resize(img, (64, 64))
    features   = extract_features(img, cv2, hog_fn)
    feat_sc    = scaler.transform(features.reshape(1, -1))

    # Get probabilities
    probs = (
        model.predict_proba(feat_sc)[0]
        if hasattr(model, "predict_proba") else None
    )

    # ── OOD gate ──────────────────────────────────────────────────────────
    if probs is not None and probs.max() < threshold:
        label     = UNKNOWN
        label_idx = -1
    else:
        label_idx = int(model.predict(feat_sc)[0])
        label     = fruit_labels[label_idx]

    emoji      = EMOJI_MAP.get(label, "❓")
    is_unknown = (label == UNKNOWN)

    # ── Console output ─────────────────────────────────────────────────────
    print("\n" + "=" * 54)
    print(f"  水果辨識結果 ({model_type.upper()} 模型)")
    print("=" * 54)
    print(f"  影像:     {os.path.basename(image_path)}")
    print(f"  預測結果: {emoji} {label}")

    if probs is not None:
        print(f"\n  各類別機率 (門檻: {threshold:.0%}):")
        for i, (fruit, prob) in enumerate(zip(fruit_labels, probs)):
            bar    = "█" * int(prob * 25)
            over   = " ← 超過門檻" if prob >= threshold else ""
            marker = " ◄ 最高" if i == label_idx else ""
            print(f"  {EMOJI_MAP.get(fruit,'?')} {fruit:<14} {bar:<26} {prob:.2%}{over}{marker}")

    if is_unknown:
        print(f"\n  ⚠️  所有類別信心度均 < {threshold:.0%}")
        print(f"  → 此影像不屬於任何已知水果類別")
    print("=" * 54)

    # ── Visualisation ──────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].imshow(img_64)
    axes[0].set_title(f"輸入影像\n{os.path.basename(image_path)}", fontsize=11)
    axes[0].axis("off")

    if probs is not None:
        bar_colors = [
            "lightgray" if is_unknown else
            ("tomato" if fruit_labels[i] == label else "steelblue")
            for i in range(len(fruit_labels))
        ]
        bars = axes[1].barh(fruit_labels, probs,
                            color=bar_colors, alpha=0.85, edgecolor="gray")
        for bar, prob in zip(bars, probs):
            axes[1].text(
                prob + 0.01, bar.get_y() + bar.get_height() / 2,
                f"{prob:.1%}", va="center", fontsize=10, fontweight="bold"
            )
        axes[1].axvline(x=threshold, color="red", linestyle="--",
                        linewidth=2, label=f"門檻 {threshold:.0%}")
        axes[1].set_xlim(0, 1.2)
        axes[1].set_xlabel("機率 (Probability)")
        axes[1].set_title("各類別預測機率", fontsize=11)
        axes[1].legend(fontsize=9)
        axes[1].grid(axis="x", alpha=0.4)

    title_color = "crimson" if is_unknown else "black"
    plt.suptitle(
        f"預測結果: {emoji} {label}  ({model_type.upper()} 模型)",
        fontsize=13, fontweight="bold", color=title_color
    )
    plt.tight_layout()
    base = os.path.splitext(os.path.basename(image_path))[0]
    out_path = f"prediction_{base}.png"
    plt.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.show()
    print(f"\n📊 結果圖表已儲存: {out_path}")

    return label, probs


def main():
    parser = argparse.ArgumentParser(
        description="水果分類預測器 — 載入已訓練模型辨識水果，非水果影像輸出「無此項目」"
    )
    parser.add_argument("--image",  required=True,
                        help="待辨識的影像路徑 (JPG/PNG)")
    parser.add_argument("--model",  default="svm", choices=["knn", "svm"],
                        help="模型類型 (預設: svm)")
    parser.add_argument("--models_dir", default="./saved_models",
                        help="模型檔案目錄 (預設: ./saved_models)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"信心度門檻 0~1 (預設: {DEFAULT_THRESHOLD})。"
                             "低於此值 → 無此項目")
    args = parser.parse_args()

    try:
        predict(args.image, args.model, args.models_dir, args.threshold)
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"\n❌ 錯誤: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 預測失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
