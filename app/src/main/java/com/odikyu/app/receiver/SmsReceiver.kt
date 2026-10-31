package com.odikyu.app.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import com.odikyu.app.data.SmsEntry
import com.odikyu.app.data.SmsRepository
import com.odikyu.app.data.SmsStore

/**
 * Handles both:
 * - [Telephony.Sms.Intents.SMS_DELIVER_ACTION] — delivered only to the default SMS app;
 *   the message is persisted into the system SMS provider.
 * - [Telephony.Sms.Intents.SMS_RECEIVED_ACTION] — legacy broadcast for non-default mode,
 *   kept so the demo still works before Odikyu is set as the default SMS app.
 */
class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        if (action != Telephony.Sms.Intents.SMS_DELIVER_ACTION &&
            action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION
        ) {
            return
        }

        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (parts.isEmpty()) return

        val sender = parts.first().originatingAddress ?: return
        val body = parts.joinToString(separator = "") { it.displayMessageBody.orEmpty() }
        if (body.isBlank()) return

        val isDefault = SmsStore.isDefaultSmsApp(context)

        // As the default app the message arrives via SMS_DELIVER and is stored in the provider;
        // skip the legacy SMS_RECEIVED duplicate (the UI syncs from the provider).
        if (action == Telephony.Sms.Intents.SMS_RECEIVED_ACTION && isDefault) return

        val providerId = if (isDefault) {
            SmsStore.insertInbox(context, sender, body, System.currentTimeMillis())
        } else {
            null
        }

        SmsRepository.add(
            SmsEntry(
                sender = sender,
                body = body,
                timestamp = System.currentTimeMillis(),
                isOutgoing = false,
                providerId = providerId,
            )
        )
    }
}
