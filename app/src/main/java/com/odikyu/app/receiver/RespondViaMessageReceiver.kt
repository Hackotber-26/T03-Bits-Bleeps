package com.odikyu.app.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.SmsManager
import android.util.Log

/**
 * Handles "respond with message" from the system call UI when Odikyu is the default SMS app.
 * Required by the default-SMS-app contract ([Telephony.Sms.Intents.RESPOND_VIA_MESSAGE_ACTION]).
 */
class RespondViaMessageReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_RESPOND_VIA_MESSAGE) return

        val number = intent.getStringExtra(EXTRA_PHONE_NUMBER) ?: return
        val text = intent.getStringExtra(EXTRA_INPUT_TEXT) ?: return

        try {
            context.getSystemService(SmsManager::class.java)
                .sendTextMessage(number, null, text, null, null)
            Log.d(TAG, "Sent respond-via-message to $number")
        } catch (e: Exception) {
            Log.w(TAG, "Failed to send respond-via-message", e)
        }
    }

    private companion object {
        const val TAG = "RespondViaMessage"
        const val ACTION_RESPOND_VIA_MESSAGE = "android.intent.action.RESPOND_VIA_MESSAGE"
        const val EXTRA_PHONE_NUMBER = "android.intent.extra.PHONE_NUMBER"
        const val EXTRA_INPUT_TEXT = "android.intent.extra.INPUT_TEXT"
    }
}
