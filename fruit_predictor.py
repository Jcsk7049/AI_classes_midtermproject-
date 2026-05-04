"""
[積分題] 獨立水果分類預測器
Standalone Fruit Classifier - loads a trained model and predicts fruit type.

Usage:
    python fruit_predictor.py --image path/to/image.jpg
    python fruit_predictor.py --image path/to/image.jpg --model knn
    python fruit_predictor.py --image path/to/image.jpg --model svm --models_dir ./saved_models
"""

import argparse
import os
import sys
import json
import numpy as np


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
    """提取 HOG + 顏色直方圖特徵 (與訓練時相同)"""
    IMG_SIZE = (64, 64)
    img = cv2.resize(img, IMG_SIZE)

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
        img_pil = Image.open(image_path).convert("RGB")
        img = np.array(img_pil)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    return img


def predict(image_path, model_type="svm", models_dir="./saved_models"):
    cv2, joblib, hog_fn, Image, plt = load_dependencies()

    # Load metadata
    meta_path = os.path.join(models_dir, "model_metadata.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            metadata = json.load(f)
        fruit_labels = metadata["fruit_labels"]
    else:
        fruit_labels = ["apple", "banana", "orange"]

    # Load model and scaler
    model_file = f"{model_type}_fruit_classifier.pkl"
    model_path = os.path.join(models_dir, model_file)
    scaler_path = os.path.join(models_dir, "feature_scaler.pkl")

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"找不到模型檔案: {model_path}\n"
            "請先執行 fruit_classification_colab.ipynb 完成訓練並儲存模型。"
        )
    if not os.path.exists(scaler_path):
        raise FileNotFoundError(f"找不到縮放器: {scaler_path}")

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    print(f"✅ 模型載入成功: {model_path}")

    # Load and process image
    img = load_image(image_path, cv2, Image)
    img_resized = cv2.resize(img, (64, 64))
    features = extract_features(img, cv2, hog_fn)
    features_scaled = scaler.transform(features.reshape(1, -1))

    # Predict
    label_idx = model.predict(features_scaled)[0]
    label = fruit_labels[label_idx]

    probs = None
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(features_scaled)[0]

    # Display results
    emoji_map = {"apple": "🍎", "banana": "🍌", "orange": "🍊"}
    emoji = emoji_map.get(label, "❓")

    print("\n" + "=" * 50)
    print(f"  水果辨識結果 ({model_type.upper()} 模型)")
    print("=" * 50)
    print(f"  影像:    {os.path.basename(image_path)}")
    print(f"  預測結果: {emoji} {label.upper()}")

    if probs is not None:
        print("\n  各類別機率:")
        for i, (fruit, prob) in enumerate(zip(fruit_labels, probs)):
            bar = "█" * int(prob * 25)
            marker = " ◄ 最高" if i == label_idx else ""
            print(f"  {emoji_map.get(fruit,'?')} {fruit:<8}  {bar:<25} {prob:.2%}{marker}")
    print("=" * 50)

    # Visualize
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].imshow(img_resized)
    axes[0].set_title(f"輸入影像\n{os.path.basename(image_path)}", fontsize=11)
    axes[0].axis("off")

    if probs is not None:
        colors = [
            "tomato" if fruit_labels[i] == label else "steelblue"
            for i in range(len(fruit_labels))
        ]
        bars = axes[1].barh(fruit_labels, probs, color=colors, alpha=0.85, edgecolor="gray")
        for bar, prob in zip(bars, probs):
            axes[1].text(
                prob + 0.01, bar.get_y() + bar.get_height() / 2,
                f"{prob:.1%}", va="center", fontsize=11, fontweight="bold"
            )
        axes[1].set_xlim(0, 1.25)
        axes[1].set_xlabel("機率 (Probability)")
        axes[1].set_title("各類別預測機率", fontsize=11)
        axes[1].grid(axis="x", alpha=0.4)

    plt.suptitle(
        f"預測結果: {emoji} {label.upper()}  ({model_type.upper()} 模型)",
        fontsize=13, fontweight="bold"
    )
    plt.tight_layout()
    out_path = f"prediction_{os.path.splitext(os.path.basename(image_path))[0]}.png"
    plt.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.show()
    print(f"\n📊 結果圖表已儲存: {out_path}")

    return label, probs


def main():
    parser = argparse.ArgumentParser(
        description="水果分類預測器 - 載入訓練模型辨識水果影像"
    )
    parser.add_argument("--image", required=True, help="待辨識的影像路徑 (JPG/PNG)")
    parser.add_argument(
        "--model", default="svm", choices=["knn", "svm"],
        help="使用的模型類型 (預設: svm)"
    )
    parser.add_argument(
        "--models_dir", default="./saved_models",
        help="模型檔案所在目錄 (預設: ./saved_models)"
    )
    args = parser.parse_args()

    try:
        label, probs = predict(args.image, args.model, args.models_dir)
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
