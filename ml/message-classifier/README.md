# Message Classifier — TFLite

TensorFlow Lite model that classifies SMS/RCS text messages into 6 categories:

1. `Safe - Personal` — human conversation (e.g. "Hey, are we meeting at 6?")
2. `Safe - Transactional` — banks/OTP/order/service notifications
3. `Promotional` — marketing/offers/loan pushes
4. `Unsafe / Suspicious` — phishing/credential bait
5. `Spam` — junk/MMS bot payloads
6. `Unclassified` — **catch-all** for messages that fit none of the above
   (random notes, app broadcasts, routing directions, Hinglish chatter…)

## Files

Runtime artifacts ship inside the Android app at `app/src/main/assets/classifier/`;
the Python dev scripts live in this folder (`ml/message-classifier/`).

| File | Purpose | Location |
|---|---|---|
| `message_classifier.tflite` | The model (~576 KB). Input: `int32[1, 64]` token IDs → Output: `float32[1, 6]` class probabilities (order = row above / `labels.json`) | `app/src/main/assets/classifier/` |
| `vocab.txt` | Token vocabulary. Line number = token ID (0-based). `0=[PAD]`, `1=[UNK]` | `app/src/main/assets/classifier/` |
| `labels.json` | Class list + input metadata (max_len = 64, input dtype = int32) | `app/src/main/assets/classifier/` |
| `preprocess.py` | The tokenization logic — tokenize exactly like this before feeding the model | this folder |
| `predict_tflite.py` | Runnable demo: `python predict_tflite.py "some message text"` (needs `tensorflow` or `ai-edge-litert`) | this folder |
| `gen_synthetic.py` | Regenerates the synthetic + augmented training CSVs | this folder |

On Android, `com.odikyu.app.data.MessageClassifier` reads the three runtime
artifacts from assets and mirrors `preprocess.py` tokenization.

## How inference works

```python
from preprocess import encode
import numpy as np

# 1. build token->id map from vocab.txt (line number = id, [PAD]=0, [UNK]=1)
tok2id = {("PAD" if i==0 else "UNK" if i==1 else tok): i
          for i, tok in enumerate(open("vocab.txt", encoding="utf-8").read().splitlines())}

# 2. tokenize: lowercase, extract [a-z0-9]+ runs, cap at 64 tokens, pad
ids = encode("Your A/C debited by INR 500", tok2id, 64)   # -> list[int]

# 3. run model
x = np.array([ids], dtype=np.int32)
interpreter.set_tensor(input_index, x)
interpreter.invoke()
probs = interpreter.get_tensor(output_index)[0]   # [p_personal, p_txn, p_promo, p_unsafe, p_spam, p_other]
```

On Android: replicate the tokenizer (Kotlin: `text.lowercase()` + regex
`[a-z#]+` after replacing digit runs `\\d+` with `#`),
map tokens via vocab.txt, fill a `TensorBuffer` with int32 IDs.

## Accuracy

~99% macro/weighted F1 on a held-out 20% split of the augmented dataset
(original + synthetic). Training data: 7,274 messages
(3,074 real + 4,200 synthetic, 6 classes, ≥700 synthetic per class,
deduplicated to 6,162). Tokenizer masks digit runs (`\d+` → `#`) so amounts
and codes don't blow up the vocab.

Caveat: synthetic rows follow template patterns, so eval metrics are
optimistic for real-world text. Keep the low-confidence fallback:
`max(probs) < 0.5` → treat as `/ review`.

## Retraining

1. `gen_synthetic.py` — regenerates the synthetic + augmented CSVs
2. `train_tflite.py` — trains on `classified_messages_augmented.csv` and
   re-exports the `.tflite`, `vocab.txt`, `labels.json`
(requires Python ≤3.13 + `tensorflow`, `pandas`, `scikit-learn`)
