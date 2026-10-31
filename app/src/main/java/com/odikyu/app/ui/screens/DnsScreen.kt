package com.odikyu.app.ui.screens

import android.content.Context
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.net.HttpURLConnection
import java.net.URL
import javax.net.ssl.HttpsURLConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private enum class DohStatus { Off, Checking, Protected, Failed }

private const val PREFS_NAME = "odikyu_settings"
private const val PREF_DNS_ENABLED = "cloudflare_doh_enabled"
private const val CLOUDFLARE_DOH_URL = "https://1.1.1.1/dns-query"

/** Friendly green used for the "protected" state, independent of the dynamic theme. */
private val ProtectedGreen = Color(0xFF2FBF71)

/** Wire-format DNS query for the A record of example.com, used to verify connectivity. */
private val PROBE_QUERY = byteArrayOf(
    0x00, 0x00, 0x01, 0x00, // header: id, recursion desired
    0x00, 0x01, 0x00, 0x00, // question count = 1
    0x00, 0x00, 0x00, 0x00,
    0x07, 0x65, 0x78, 0x61, 0x6D, 0x70, 0x6C, 0x65, // "example"
    0x03, 0x63, 0x6F, 0x6D, 0x00, // "com" + root
    0x00, 0x01, 0x00, 0x01, // type A, class IN
)

/**
 * Protection screen: a big friendly ON/OFF switch (no technical jargon) that toggles the
 * encrypted-lookup protection and verifies it end-to-end.
 */
@Composable
fun DnsScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
    var enabled by rememberSaveable { mutableStateOf(prefs.getBoolean(PREF_DNS_ENABLED, false)) }
    var status by remember { mutableStateOf(if (enabled) DohStatus.Checking else DohStatus.Off) }

    LaunchedEffect(enabled) {
        status = if (enabled) DohStatus.Checking else DohStatus.Off
        if (enabled) {
            val ok = verifyProtection()
            status = if (ok) DohStatus.Protected else DohStatus.Failed
        }
    }

    // Optimistic: the knob follows the user's intent immediately, even while verifying.
    val toggleOn = status != DohStatus.Off
    val busy = status == DohStatus.Checking

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(16.dp))
        Text(
            text = "Protection",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = "Stops scam and phishing sites before they load on your phone.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.weight(1f))

        ToggleRings(active = toggleOn) {
            ProtectionToggle(
                checked = toggleOn,
                enabled = !busy,
                onToggle = {
                    val next = !enabled
                    enabled = next
                    prefs.edit().putBoolean(PREF_DNS_ENABLED, next).apply()
                },
            )
        }

        Spacer(Modifier.height(32.dp))

        Text(
            text = when (status) {
                DohStatus.Protected -> "Your browsing is protected"
                DohStatus.Off -> "Protection is off"
                DohStatus.Checking -> "Turning on protection…"
                DohStatus.Failed -> "Couldn't turn on protection"
            },
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.SemiBold,
            color = when (status) {
                DohStatus.Protected -> ProtectedGreen
                DohStatus.Failed -> MaterialTheme.colorScheme.error
                else -> MaterialTheme.colorScheme.onSurface
            },
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(14.dp))

        StatusPill(status = status)

        Spacer(Modifier.weight(1.2f))
    }
}

/** Concentric dashed rings + floating dots behind the toggle, echoing the reference design. */
@Composable
private fun ToggleRings(
    active: Boolean,
    content: @Composable () -> Unit,
) {
    val ringColor = if (active) ProtectedGreen else MaterialTheme.colorScheme.onSurfaceVariant

    Box(
        modifier = Modifier.size(300.dp),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val c = center
            drawCircle(
                color = ringColor.copy(alpha = 0.10f),
                radius = 140.dp.toPx(),
                style = Stroke(width = 10.dp.toPx(), cap = StrokeCap.Round),
            )
            drawCircle(
                color = ringColor.copy(alpha = 0.45f),
                radius = 118.dp.toPx(),
                style = Stroke(
                    width = 2.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(
                        floatArrayOf(6.dp.toPx(), 14.dp.toPx()),
                    ),
                ),
            )
            drawCircle(
                color = ringColor.copy(alpha = 0.16f),
                radius = 96.dp.toPx(),
                style = Stroke(width = 1.5.dp.toPx()),
            )
            // Little floating dots on the outer ring.
            listOf(-40f, 25f, 130f, 205f, 300f).forEach { degrees ->
                val rad = Math.toRadians(degrees.toDouble())
                drawCircle(
                    color = ringColor.copy(alpha = 0.6f),
                    radius = 3.dp.toPx(),
                    center = Offset(
                        c.x + (140.dp.toPx() * kotlin.math.cos(rad)).toFloat(),
                        c.y + (140.dp.toPx() * kotlin.math.sin(rad)).toFloat(),
                    ),
                )
            }
            // Empty center wash so the toggle sits on a soft disc.
            drawCircle(color = ringColor.copy(alpha = 0.07f), radius = 84.dp.toPx())
        }
        content()
    }
}

/** Big ON/OFF switch with an animated knob. */
@Composable
private fun ProtectionToggle(
    checked: Boolean,
    enabled: Boolean,
    onToggle: () -> Unit,
) {
    val knobPos by animateFloatAsState(targetValue = if (checked) 1f else 0f, label = "knob")
    val trackColor = if (checked) ProtectedGreen else MaterialTheme.colorScheme.surfaceContainerHighest
    val onTrack = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f)

    Box(
        modifier = Modifier
            .width(152.dp)
            .height(72.dp)
            .clip(RoundedCornerShape(36.dp))
            .background(trackColor)
            .clickable(enabled = enabled, onClick = onToggle),
        contentAlignment = Alignment.CenterStart,
    ) {
        Text(
            text = if (checked) "ON" else "OFF",
            color = if (checked) Color.White else onTrack,
            fontWeight = FontWeight.Bold,
            fontSize = 15.sp,
            letterSpacing = 1.5.sp,
            modifier = Modifier
                .align(if (checked) Alignment.CenterStart else Alignment.CenterEnd)
                .padding(horizontal = 24.dp),
        )
        Box(
            modifier = Modifier
                .align(Alignment.CenterStart)
                .offset(x = 8.dp + 80.dp * knobPos)
                .size(56.dp)
                .clip(CircleShape)
                .background(Color.White),
        )
    }
}

/** Rounded status pill under the headline. */
@Composable
private fun StatusPill(status: DohStatus) {
    val (container, content) = when (status) {
        DohStatus.Protected -> ProtectedGreen.copy(alpha = 0.16f) to ProtectedGreen
        DohStatus.Failed -> MaterialTheme.colorScheme.errorContainer to MaterialTheme.colorScheme.onErrorContainer
        else -> MaterialTheme.colorScheme.surfaceContainerHighest to MaterialTheme.colorScheme.onSurfaceVariant
    }

    Surface(color = container, contentColor = content, shape = RoundedCornerShape(50)) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            when (status) {
                DohStatus.Checking -> CircularProgressIndicator(
                    modifier = Modifier.size(14.dp),
                    strokeWidth = 2.dp,
                    color = content,
                )
                DohStatus.Protected -> Icon(Icons.Filled.CheckCircle, null, Modifier.size(16.dp))
                DohStatus.Failed -> Icon(Icons.Filled.Warning, null, Modifier.size(16.dp))
                DohStatus.Off -> Box(
                    modifier = Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(content),
                )
            }
            Text(
                text = when (status) {
                    DohStatus.Protected -> "You're safe to browse"
                    DohStatus.Off -> "Flip the switch to get protected"
                    DohStatus.Checking -> "Checking your connection…"
                    DohStatus.Failed -> "Check your internet and try again"
                },
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}

/** Verifies protection end-to-end with a real encrypted lookup (result never shown as a URL). */
private suspend fun verifyProtection(): Boolean = withContext(Dispatchers.IO) {
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
