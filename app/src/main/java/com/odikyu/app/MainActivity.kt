package com.odikyu.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import com.odikyu.app.ui.navigation.OdikyuApp
import com.odikyu.app.ui.theme.OdikyuTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val prefillNumber = prefillNumberFrom(intent)
        setContent {
            OdikyuTheme {
                OdikyuApp(
                    modifier = Modifier.fillMaxSize(),
                    prefillNumber = prefillNumber,
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        // SENDTO (smsto:/sms:) intents may arrive while the activity is alive; ignore for now —
        // the prefill at launch covers the common case.
    }

    /** Extracts the recipient from `smsto:+12345` style SENDTO intents. */
    private fun prefillNumberFrom(intent: Intent?): String? =
        if (intent?.action == Intent.ACTION_SENDTO) intent.data?.schemeSpecificPart else null
}
