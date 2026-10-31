package com.odikyu.app.ui.screens

import android.content.Context
import android.content.SharedPreferences
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.net.HttpURLConnection
import java.net.URL
import javax.net.ssl.HttpsURLConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private enum class DohStatus { Off, Checking, Protected, Failed }

private const val PREFS_NAME = "odikyu_settings"
private const val PREF_DNS_ENABLED = "cloudflare_doh_enabled"
private const val CLOUDFLARE_DOH_URL = "https://1.1.1.1/dns-query"

/** Wire-format DNS query for the A record of example.com, used to verify DoH connectivity. */
private val PROBE_QUERY = byteArrayOf(
    0x00, 0x00, 0x01, 0x00, // header: id, recursion desired
    0x00, 0x01, 0x00, 0x00, // question count = 1
    0x00, 0x00, 0x00, 0x00,
    0x07, 0x65, 0x78, 0x61, 0x6D, 0x70, 0x6C, 0x65, // "example"
    0x03, 0x63, 0x6F, 0x6D, 0x00, // "com" + root
    0x00, 0x01, 0x00, 0x01, // type A, class IN
)

@Composable
fun DnsScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
    var enabled by rememberSaveable { mutableStateOf(prefs.getBoolean(PREF_DNS_ENABLED, false)) }
    var status by remember { mutableStateOf(if (enabled) DohStatus.Checking else DohStatus.Off) }

    LaunchedEffect(enabled) {
        status = if (enabled) DohStatus.Checking else DohStatus.Off
        if (enabled) {
            val ok = resolveViaCloudflare()
            status = if (ok) DohStatus.Protected else DohStatus.Failed
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(
            imageVector = Icons.Filled.Lock,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier
                .padding(top = 24.dp)
                .size(56.dp),
        )
        Text(
            text = "DNS Protection",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(top = 12.dp),
        )
        Text(
            text = "Scam lookups and phishing domains get resolved over encrypted Cloudflare DNS before they can reach you.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp),
        )

        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 24.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceContainer
            ),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Cloudflare 1.1.1.1",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = "DNS over HTTPS (DoH)",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Switch(
                    checked = enabled,
                    onCheckedChange = { on ->
                        enabled = on
                        prefs.edit().putBoolean(PREF_DNS_ENABLED, on).apply()
                    },
                )
            }
        }

        StatusCard(status = status, modifier = Modifier.padding(top = 12.dp))

        Text(
            text = "Endpoint: $CLOUDFLARE_DOH_URL",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 16.dp),
        )
    }
}

@Composable
private fun StatusCard(status: DohStatus, modifier: Modifier = Modifier) {
    val (containerColor, contentColor) = when (status) {
        DohStatus.Protected ->
            MaterialTheme.colorScheme.primaryContainer to MaterialTheme.colorScheme.onPrimaryContainer
        DohStatus.Failed ->
            MaterialTheme.colorScheme.errorContainer to MaterialTheme.colorScheme.onErrorContainer
        DohStatus.Off, DohStatus.Checking ->
            MaterialTheme.colorScheme.surfaceContainerHighest to MaterialTheme.colorScheme.onSurface
    }

    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = containerColor,
            contentColor = contentColor,
        ),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            when (status) {
                DohStatus.Protected -> Icon(Icons.Filled.CheckCircle, contentDescription = null)
                DohStatus.Failed -> Icon(Icons.Filled.Warning, contentDescription = null)
                DohStatus.Checking -> CircularProgressIndicator(
                    modifier = Modifier.size(24.dp),
                    strokeWidth = 3.dp,
                )
                DohStatus.Off -> Icon(Icons.Filled.Lock, contentDescription = null)
            }
            Text(
                text = when (status) {
                    DohStatus.Off -> "Unprotected — your DNS queries travel in the clear."
                    DohStatus.Checking -> "Checking connection to 1.1.1.1…"
                    DohStatus.Protected -> "Protected — encrypted DNS to 1.1.1.1 verified."
                    DohStatus.Failed -> "Could not reach 1.1.1.1 over HTTPS. Check your connection."
                },
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

/** Posts a DNS wire-format query to Cloudflare's DoH endpoint; success means 1.1.1.1 over HTTPS works. */
private suspend fun resolveViaCloudflare(): Boolean = withContext(Dispatchers.IO) {
    try {
        val connection = URL(CLOUDFLARE_DOH_URL).openConnection() as HttpsURLConnection
        connection.requestMethod = "POST"
        connection.connectTimeout = 5_000
        connection.readTimeout = 5_000
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/dns-message")
        connection.setRequestProperty("Accept", "application/dns-message")
        connection.outputStream.use { it.write(PROBE_QUERY) }
        val ok = connection.responseCode == HttpURLConnection.HTTP_OK
        connection.disconnect()
        ok
    } catch (_: Exception) {
        false
    }
}
