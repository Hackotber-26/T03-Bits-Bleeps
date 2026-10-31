package com.odikyu.app.service

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.telephony.SmsManager
import android.util.Log

/**
 * Handles "respond with message" from the system call UI when Odikyu is the default SMS app.
 *
 * The system sends [android.intent.action.RESPOND_VIA_MESSAGE] via `startService()`, so this must
 * be a service (with `android:permission="android.permission.SEND_RESPOND_VIA_MESSAGE"` and an
 * `smsto` scheme in the intent filter) to qualify Odikyu for the default-SMS-app role.
 */
class RespondViaMessageService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_RESPOND_VIA_MESSAGE) {
            val number = intent.getStringExtra(EXTRA_PHONE_NUMBER)
            val text = intent.getStringExtra(EXTRA_INPUT_TEXT)
            if (number != null && text != null) {
                try {
                    getSystemService(SmsManager::class.java)
                        .sendTextMessage(number, null, text, null, null)
                    Log.d(TAG, "Sent respond-via-message to $number")
                } catch (e: Exception) {
                    Log.w(TAG, "Failed to send respond-via-message", e)
                }
            }
        }
        stopSelf(startId)
        return START_NOT_STICKY
    }

    private companion object {
        const val TAG = "RespondViaMessage"
        const val ACTION_RESPOND_VIA_MESSAGE = "android.intent.action.RESPOND_VIA_MESSAGE"
        const val EXTRA_PHONE_NUMBER = "android.intent.extra.PHONE_NUMBER"
        const val EXTRA_INPUT_TEXT = "android.intent.extra.INPUT_TEXT"
    }
}
