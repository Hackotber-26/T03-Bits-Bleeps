package com.odikyu.app.data

import android.graphics.BitmapFactory
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/** Loads and caches website favicons via Google's public favicon service. */
object FaviconStore {

    private const val ENDPOINT = "https://www.google.com/s2/favicons?domain=%s&sz=64"
    private const val TIMEOUT_MS = 5_000

    private val cache = HashMap<String, ImageBitmap?>()

    /**
     * Returns the favicon for [domain] (e.g. "jio.com"), or null when unavailable.
     * Results — including failures — are cached so each domain is fetched at most once.
     */
    suspend fun load(domain: String): ImageBitmap? {
        if (domain.isBlank()) return null
        synchronized(cache) {
            if (cache.containsKey(domain)) return cache[domain]
        }
        val bitmap = withContext(Dispatchers.IO) {
            try {
                val connection = URL(ENDPOINT.format(domain)).openConnection() as HttpURLConnection
                connection.connectTimeout = TIMEOUT_MS
                connection.readTimeout = TIMEOUT_MS
                // Unknown domains come back as 404 — but with Google's fallback icon as the body.
                val stream = if (connection.responseCode in 200..299) {
                    connection.inputStream
                } else {
                    connection.errorStream
                }
                stream?.use { BitmapFactory.decodeStream(it)?.asImageBitmap() }
            } catch (_: Exception) {
                null
            }
        }
        synchronized(cache) { cache[domain] = bitmap }
        return bitmap
    }
}
