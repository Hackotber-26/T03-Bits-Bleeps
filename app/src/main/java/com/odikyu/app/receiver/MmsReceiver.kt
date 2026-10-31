package com.odikyu.app.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log

/**
 * Required for Odikyu to qualify as the default SMS app ([Telephony.Sms.Intents.WAP_PUSH_DELIVER_ACTION]).
 * MMS handling is out of scope for now; the broadcast is simply accepted so MMS isn't dropped
 * silently by the system.
 */
class MmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Telephony.Sms.Intents.WAP_PUSH_DELIVER_ACTION) {
            Log.d(TAG, "MMS delivered — handling not implemented yet")
        }
    }

    private companion object {
        const val TAG = "MmsReceiver"
    }
}
