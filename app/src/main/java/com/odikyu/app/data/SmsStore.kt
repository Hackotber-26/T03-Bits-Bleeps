package com.odikyu.app.data

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.provider.Telephony

/**
 * Bridge to the system SMS provider. When Odikyu is the default SMS app it can read/write the
 * shared SMS store; messages then survive restarts and appear in the conversation history.
 */
object SmsStore {

    fun isDefaultSmsApp(context: Context): Boolean =
        Telephony.Sms.getDefaultSmsPackage(context) == context.packageName

    /**
     * Looks up the conversation thread id for [address] so stored messages line up into a
     * conversation. Returns null if unavailable (Odikyu is not the default SMS app).
     */
    private fun threadIdFor(context: Context, address: String): Long? = try {
        val uri = Uri.parse("content://mms-sms/conversation")
            .buildUpon()
            .appendQueryParameter("recipient", address)
            .build()
        context.contentResolver.query(uri, arrayOf("_id"), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getLong(0) else null
        }
    } catch (_: Exception) {
        null
    }

    /** Inserts a received message into the inbox; returns its provider id, or null on failure. */
    fun insertInbox(context: Context, address: String, body: String, timestamp: Long): Long? =
        insert(
            context = context,
            uri = Telephony.Sms.Inbox.CONTENT_URI,
            address = address,
            body = body,
            timestamp = timestamp,
            type = Telephony.Sms.MESSAGE_TYPE_INBOX,
            read = 0,
        )

    /** Inserts a sent message into the sent folder; returns its provider id, or null on failure. */
    fun insertSent(context: Context, address: String, body: String, timestamp: Long): Long? =
        insert(
            context = context,
            uri = Telephony.Sms.Sent.CONTENT_URI,
            address = address,
            body = body,
            timestamp = timestamp,
            type = Telephony.Sms.MESSAGE_TYPE_SENT,
            read = 1,
        )

    private fun insert(
        context: Context,
        uri: Uri,
        address: String,
        body: String,
        timestamp: Long,
        type: Int,
        read: Int,
    ): Long? = try {
        val values = ContentValues().apply {
            put(Telephony.Sms.ADDRESS, address)
            put(Telephony.Sms.BODY, body)
            put(Telephony.Sms.DATE, timestamp)
            put(Telephony.Sms.DATE_SENT, timestamp)
            put(Telephony.Sms.TYPE, type)
            put(Telephony.Sms.READ, read)
            put(Telephony.Sms.SEEN, read)
            threadIdFor(context, address)?.let { put(Telephony.Sms.THREAD_ID, it) }
        }
        context.contentResolver.insert(uri, values)?.lastPathSegment?.toLongOrNull()
    } catch (_: Exception) {
        null
    }

    /**
     * Reads inbox + sent messages from the provider (chronological).
     * Returns null when Odikyu can't read the store (not the default SMS app).
     */
    fun readAll(context: Context): List<SmsEntry>? = try {
        val projection = arrayOf(
            Telephony.Sms._ID,
            Telephony.Sms.ADDRESS,
            Telephony.Sms.BODY,
            Telephony.Sms.DATE,
            Telephony.Sms.TYPE,
        )
        context.contentResolver.query(
            Telephony.Sms.CONTENT_URI,
            projection,
            "${Telephony.Sms.TYPE} IN (?, ?)",
            arrayOf(
                Telephony.Sms.MESSAGE_TYPE_INBOX.toString(),
                Telephony.Sms.MESSAGE_TYPE_SENT.toString(),
            ),
            "${Telephony.Sms.DATE} ASC",
        )?.use { cursor ->
            val idCol = cursor.getColumnIndexOrThrow(Telephony.Sms._ID)
            val addressCol = cursor.getColumnIndexOrThrow(Telephony.Sms.ADDRESS)
            val bodyCol = cursor.getColumnIndexOrThrow(Telephony.Sms.BODY)
            val dateCol = cursor.getColumnIndexOrThrow(Telephony.Sms.DATE)
            val typeCol = cursor.getColumnIndexOrThrow(Telephony.Sms.TYPE)

            buildList {
                while (cursor.moveToNext()) {
                    val body = cursor.getString(bodyCol) ?: continue
                    if (body.isBlank()) continue
                    add(
                        SmsEntry(
                            sender = cursor.getString(addressCol) ?: "Unknown",
                            body = body,
                            timestamp = cursor.getLong(dateCol),
                            isOutgoing = cursor.getInt(typeCol) == Telephony.Sms.MESSAGE_TYPE_SENT,
                            providerId = cursor.getLong(idCol),
                        )
                    )
                }
            }
        }
    } catch (_: Exception) {
        null
    }
}
