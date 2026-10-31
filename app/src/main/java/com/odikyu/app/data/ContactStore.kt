package com.odikyu.app.data

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.ContactsContract
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext

/** Resolved contact details for an SMS address. */
data class ContactInfo(val name: String, val photoUri: Uri?)

/**
 * Looks up contact names and profile photos for phone numbers.
 * Requires READ_CONTACTS; all queries are best-effort and degrade to null on any failure.
 */
object ContactStore {

    private val _contacts = MutableStateFlow<Map<String, ContactInfo>>(emptyMap())
    val contacts = _contacts.asStateFlow()

    private val photoCache = HashMap<String, ImageBitmap?>()
    private val resolved = HashSet<String>()

    /** Resolves any addresses we haven't looked up yet. Safe to call repeatedly. */
    suspend fun resolve(context: Context, addresses: Collection<String>) = withContext(Dispatchers.IO) {
        val pending = synchronized(resolved) {
            addresses.filter { it.isNotBlank() && resolved.add(it) }
        }
        pending.forEach { address ->
            queryContact(context, address)?.let { info ->
                _contacts.update { it + (address to info) }
            }
        }
    }

    fun nameFor(address: String): String? = _contacts.value[address]?.name

    /** Loads and caches the contact's photo for [address]; null if none/unavailable. */
    suspend fun loadPhoto(context: Context, address: String): ImageBitmap? {
        photoCache[address]?.let { return it }
        val uri = _contacts.value[address]?.photoUri ?: return null
        val bitmap = withContext(Dispatchers.IO) {
            try {
                context.contentResolver.openInputStream(uri)?.use { stream ->
                    BitmapFactory.decodeStream(stream)?.asImageBitmap()
                }
            } catch (_: Exception) {
                null
            }
        }
        photoCache[address] = bitmap
        return bitmap
    }

    private fun queryContact(context: Context, address: String): ContactInfo? = try {
        val lookupUri = Uri.withAppendedPath(
            ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
            Uri.encode(address),
        )
        context.contentResolver.query(
            lookupUri,
            arrayOf(
                ContactsContract.PhoneLookup.DISPLAY_NAME,
                ContactsContract.PhoneLookup.PHOTO_URI,
            ),
            null,
            null,
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) {
                val name = cursor.getString(0)?.takeIf { it.isNotBlank() } ?: return null
                ContactInfo(name = name, photoUri = cursor.getString(1)?.let(Uri::parse))
            } else {
                null
            }
        }
    } catch (_: Exception) {
        null
    }
}
