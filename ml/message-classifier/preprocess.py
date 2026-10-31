"""
Shared text tokenization for training and TFLite inference.
TFLite does not support string ops, so tokenization lives outside the model:
the .tflite model takes int32 token indices (0=pad, 1=unk).
"""
import re

PAD_ID = 0
UNK_ID = 1

_TOKEN_RE = re.compile(r"[a-z#]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, mask digit runs as '#', split on non-alphanumerics.
    Must match training exactly."""
    masked = re.sub(r"\d+", "#", str(text).lower())
    return _TOKEN_RE.findall(masked)


def encode(text: str, vocab: dict[str, int], max_len: int) -> list[int]:
    toks = tokenize(text)[:max_len]
    return [vocab.get(t, UNK_ID) for t in toks] + [PAD_ID] * (max_len - len(toks))


def build_vocab(texts, max_tokens: int = 8000):
    from collections import Counter
    counts = Counter()
    for t in texts:
        counts.update(tokenize(t))
    vocab = {"[PAD]": PAD_ID, "[UNK]": UNK_ID}
    for tok, _ in counts.most_common(max_tokens):
        vocab[tok] = len(vocab)
    return vocab
