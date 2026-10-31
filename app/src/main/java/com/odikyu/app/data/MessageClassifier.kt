package com.odikyu.app.data

import android.content.Context
import android.util.Log
import org.json.JSONObject
import org.tensorflow.lite.Interpreter
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** The six classes the TFLite model can predict; matched to output indices via labels.json. */
enum class MessageCategory(val modelLabel: String) {
    PROMOTIONAL("Promotional"),
    TRANSACTIONAL("Safe - Transactional"),
    PERSONAL("Safe - Personal"),
    UNSAFE("Unsafe / Suspicious"),
    SPAM("Spam"),
    UNCLASSIFIED("Unclassified");

    companion object {
        fun fromLabel(label: String): MessageCategory? =
            entries.firstOrNull { it.modelLabel == label }
    }
}

/** One model verdict for a message body. */
data class Classification(val category: MessageCategory, val confidence: Float)

/**
 * Tokenizes text exactly like ml/message-classifier/preprocess.py (which mirrors training):
 * lowercase, mask digit runs as `#`, split on `[a-z#]+` runs, map tokens via vocab line
 * numbers, cap at [maxLen], pad with 0. Kept free of Android/TFLite types so it is
 * unit-testable on the JVM.
 */
internal fun encode(text: String, vocab: Map<String, Int>, maxLen: Int): IntArray {
    val ids = IntArray(maxLen) // 0 == PAD_ID
    var i = 0
    for (match in TOKEN_RE.findAll(DIGIT_RUN.replace(text.lowercase(), "#"))) {
        if (i >= maxLen) break
        ids[i] = vocab[match.value] ?: UNK_ID
        i++
    }
    return ids
}

private const val PAD_ID = 0
private const val UNK_ID = 1
private val DIGIT_RUN = Regex("\\d+")
private val TOKEN_RE = Regex("[a-z#]+")

/**
 * On-device SMS classifier backed by assets/classifier/ (model + vocab.txt + labels.json).
 *
 * The interpreter is single-threaded (TFLite interpreters are not thread-safe), so every
 * call is serialized behind one lock; verdicts are cached per message body because the UI
 * re-classifies the same texts on every recomposition. Failures degrade to `null`,
 * which the UI renders as an ordinary message card.
 */
object MessageClassifier {

    private const val TAG = "Odikyu"
    private const val MODEL_ASSET = "classifier/message_classifier.tflite"
    private const val VOCAB_ASSET = "classifier/vocab.txt"
    private const val LABELS_ASSET = "classifier/labels.json"
    private const val MAX_CACHE_ENTRIES = 256

    private val lock = Any()

    private var interpreter: Interpreter? = null
    private var tokenToId: Map<String, Int> = emptyMap()
    private var labels: List<String> = emptyList()
    private var maxLength = 64
    private var loadFailed = false

    private val cache = object : LinkedHashMap<String, Classification?>(32, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Classification?>) =
            size > MAX_CACHE_ENTRIES
    }

    /**
     * Classifies a message body. Returns null when the text is empty, the model could not
     * be loaded, or no known label matched. Safe to call from any thread (blocks briefly
     * while another classification is in flight).
     */
    fun classify(context: Context, text: String): Classification? {
        if (text.isBlank()) return null
        synchronized(lock) {
            cache[text]?.let { return it }
            val result = if (loadFailed) {
                null
            } else {
                runCatching { infer(context.applicationContext, text) }
                    .onFailure { Log.e(TAG, "message classification failed", it) }
                    .getOrNull()
            }
            cache[text] = result
            return result
        }
    }

    private fun infer(context: Context, text: String): Classification? {
        val model = interpreter ?: load(context) ?: return null
        val input = Array(1) { encode(text, tokenToId, maxLength) }
        val output = Array(1) { FloatArray(labels.size) }
        model.run(input, output)
        val probs = output[0]
        val best = probs.indices.maxBy { probs[it] }
        val category = MessageCategory.fromLabel(labels[best]) ?: return null
        return Classification(category, probs[best])
    }

    /** Loads vocab + labels + model from assets. Caller must hold [lock]. */
    private fun load(context: Context): Interpreter? {
        try {
            val meta = context.assets.open(LABELS_ASSET)
                .bufferedReader().use { JSONObject(it.readText()) }
            val labelArray = meta.getJSONArray("labels")
            labels = List(labelArray.length()) { labelArray.getString(it) }
            maxLength = meta.getInt("max_len")

            // Line number = token id (0=[PAD], 1=[UNK]); readLines() strips the file's CRLFs.
            tokenToId = context.assets.open(VOCAB_ASSET)
                .bufferedReader().use { reader ->
                    reader.readLines().mapIndexedNotNull { i, tok -> tok to i }.toMap()
                }

            // Load the flatbuffer into a direct buffer: works whether or not aapt
            // stores the asset uncompressed, with no cache file to invalidate.
            val bytes = context.assets.open(MODEL_ASSET).use { it.readBytes() }
            val buffer = ByteBuffer.allocateDirect(bytes.size).order(ByteOrder.nativeOrder())
            buffer.put(bytes).rewind()

            return Interpreter(buffer, Interpreter.Options().apply { numThreads = 2 })
                .also { interpreter = it }
        } catch (e: Exception) {
            loadFailed = true
            Log.e(TAG, "failed to load message classifier assets", e)
            return null
        }
    }
}
