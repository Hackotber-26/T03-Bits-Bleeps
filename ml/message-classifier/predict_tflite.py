"""
CLI demo for the exported TFLite classifier.
Usage:
  .venv/Scripts/python.exe predict_tflite.py "Your A/C debited by INR 500 ..." ["message 2" ...]
  .venv/Scripts/python.exe predict_tflite.py            # runs built-in sample messages
"""
import sys
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent

# lazily import tflite runtime
import tensorflow as tf  # noqa: E402  (demo uses full TF; on-device use runtime)

from preprocess import encode  # noqa: E402

with open(ROOT / "labels.json", encoding="utf-8") as f:
    meta = json.load(f)
labels = meta["labels"]
MAX_LEN = meta["max_len"]

# ids are 0-based line numbers in vocab.txt (0=[PAD], 1=[UNK])
token_to_id = {
    ("[PAD]" if i == 0 else ("[UNK]" if i == 1 else tok)): i
    for i, tok in enumerate(
        (ROOT / "vocab.txt").read_text(encoding="utf-8").splitlines()
    )
}

interp = tf.lite.Interpreter(model_path=str(ROOT / "message_classifier.tflite"))
interp.allocate_tensors()
inp = interp.get_input_details()[0]
out = interp.get_output_details()[0]
print(f"tflite input: {inp['shape']} {np.dtype(inp['dtype']).name}, "
      f"output: {out['shape']}")


def classify(text: str) -> tuple[str, float, list[float]]:
    x = np.array([encode(text, token_to_id, MAX_LEN)], dtype=inp["dtype"])
    interp.set_tensor(inp["index"], x)
    interp.invoke()
    probs = interp.get_tensor(out["index"])[0]
    best = int(np.argmax(probs))
    return labels[best], float(probs[best]), probs.tolist()


SAMPLES = [
    "Your A/C XXXXX159255 is debited by INR 250.00 on 31/10/25. New Bal :INR 6,578.63. Team IDFC FIRST Bank",
    "Hey, are we still meeting at 6 today?",
    "Congrats!! You have been pre-approved for a Rs.500000 loan with 0% interest. Click bit.ly/xYz",
    "URGENT: your account will be blocked, click this shortened link and enter net banking user id and password",
    "ok",
    "reminder: pick up the dry cleaning tomorrow",
    "wifi password is HGTRE99 please dont share",
    "This quiz app is rigged I swear",
]


def main():
    texts = sys.argv[1:] or SAMPLES
    for t in texts:
        label, conf, probs = classify(t)
        top = sorted(zip(labels, probs), key=lambda p: -p[1])[:2]
        print(f"\nTEXT: {t[:100]}{'...' if len(t) > 100 else ''}")
        print(f"  -> {label}  (confidence {conf:.2f})"
              f"  | top-2: {[f'{l}={p:.2f}' for l, p in top]}")


if __name__ == "__main__":
    main()
