package com.odikyu.app.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import com.odikyu.app.data.SmsEntry
import com.odikyu.app.data.SmsRepository

/** Receives incoming SMS broadcasts and stores them in [SmsRepository]. */
class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (parts.isEmpty()) return

        val sender = parts.first().originatingAddress ?: return
        val body = parts.joinToString(separator = "") { it.displayMessageBody.orEmpty() }

        if (body.isNotBlank()) {
            SmsRepository.add(
                SmsEntry(
                    sender = sender,
                    body = body,
                    timestamp = System.currentTimeMillis(),
                    isOutgoing = false,
                )
            )
        }
    }
}
