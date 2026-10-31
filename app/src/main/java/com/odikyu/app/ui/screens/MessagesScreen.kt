package com.odikyu.app.ui.screens

import android.Manifest
import android.app.role.RoleManager
import android.content.Intent
import android.content.pm.PackageManager
import android.database.ContentObserver
import android.os.Handler
import android.os.Looper
import android.provider.Telephony
import android.telephony.SmsManager
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.LifecycleOwner
import com.odikyu.app.data.Links
import com.odikyu.app.data.SmsEntry
import com.odikyu.app.data.SmsRepository
import com.odikyu.app.data.SmsStore
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val REQUIRED_PERMISSIONS = listOf(
    Manifest.permission.SEND_SMS,
    Manifest.permission.RECEIVE_SMS,
)

private val TIME_FORMAT = DateTimeFormatter.ofPattern("EEE HH:mm")

@Composable
fun MessagesScreen(modifier: Modifier = Modifier, initialNumber: String? = null) {
    val context = LocalContext.current
    val messages by SmsRepository.messages.collectAsState()
    var number by remember { mutableStateOf(initialNumber.orEmpty()) }
    var body by remember { mutableStateOf("") }
    var isDefault by remember { mutableStateOf(SmsStore.isDefaultSmsApp(context)) }
    val listState = rememberLazyListState()

    /** Re-checks default status and, when default, reloads history from the system provider. */
    fun refresh() {
        val nowDefault = SmsStore.isDefaultSmsApp(context)
        android.util.Log.i("Odikyu", "refresh: isDefault=$nowDefault")
        isDefault = nowDefault
        if (nowDefault) {
            SmsStore.readAll(context)?.let { SmsRepository.replaceAll(it) }
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        if (!grants.values.all { it }) {
            Toast.makeText(
                context,
                "Odikyu needs SMS permissions to send and receive messages",
                Toast.LENGTH_LONG,
            ).show()
        }
    }

    val changeDefaultLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { refresh() }

    LaunchedEffect(Unit) {
        val missing = REQUIRED_PERMISSIONS.filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            permissionLauncher.launch(missing.toTypedArray())
        }
        refresh()
    }

    // Watch the system SMS store so provider-side changes (incoming messages, sync) show up live.
    DisposableEffect(Unit) {
        val observer = object : ContentObserver(Handler(Looper.getMainLooper())) {
            override fun onChange(selfChange: Boolean) {
                refresh()
            }
        }
        context.contentResolver.registerContentObserver(Telephony.Sms.CONTENT_URI, true, observer)
        onDispose { context.contentResolver.unregisterContentObserver(observer) }
    }

    // Re-check default status whenever the app returns to the foreground (e.g. after the
    // system "Set as default" dialog closes, whose activity result can race the role update).
    DisposableEffect(context) {
        val lifecycleOwner = context as? LifecycleOwner
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) refresh()
        }
        lifecycleOwner?.lifecycle?.addObserver(observer)
        onDispose { lifecycleOwner?.lifecycle?.removeObserver(observer) }
    }

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.lastIndex)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .imePadding()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Messages",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.weight(1f),
            )
            if (messages.isNotEmpty()) {
                IconButton(onClick = { SmsRepository.clear() }) {
                    Icon(Icons.Filled.Delete, contentDescription = "Clear messages")
                }
            }
        }

        if (!isDefault) {
            DefaultSmsBanner(
                onMakeDefault = {
                    try {
                        val roleManager = context.getSystemService(RoleManager::class.java)
                        if (roleManager != null && roleManager.isRoleAvailable(RoleManager.ROLE_SMS)) {
                            changeDefaultLauncher.launch(
                                roleManager.createRequestRoleIntent(RoleManager.ROLE_SMS)
                            )
                        } else {
                            // Legacy fallback for OEM builds without the role service.
                            changeDefaultLauncher.launch(
                                Intent(Telephony.Sms.Intents.ACTION_CHANGE_DEFAULT).apply {
                                    putExtra(Telephony.Sms.Intents.EXTRA_PACKAGE_NAME, context.packageName)
                                }
                            )
                        }
                    } catch (e: Exception) {
                        Toast.makeText(
                            context,
                            "Couldn't open the default SMS app picker: ${e.message}",
                            Toast.LENGTH_LONG,
                        ).show()
                    }
                },
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }

        if (messages.isEmpty()) {
            Text(
                text = "No messages yet. Incoming SMS will appear here, and you can send one below.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(16.dp),
            )
        }

        LazyColumn(
            state = listState,
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(messages, key = { it.providerId ?: (it.timestamp * 1000 + it.hashCode()) }) { entry ->
                MessageBubble(entry)
            }
        }

        Surface(tonalElevation = 1.dp) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = number,
                    onValueChange = { number = it },
                    label = { Text("To") },
                    placeholder = { Text("+1 555 000 1234") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = body,
                    onValueChange = { body = it },
                    label = { Text("Message") },
                    singleLine = false,
                    modifier = Modifier.weight(2f),
                )
                OutlinedButton(
                    onClick = {
                        val result = sendSms(context, number, body)
                        result.onSuccess { sentBody ->
                            val timestamp = System.currentTimeMillis()
                            val address = number.trim()
                            val providerId = if (isDefault) {
                                SmsStore.insertSent(context, address, sentBody, timestamp)
                            } else {
                                null
                            }
                            SmsRepository.add(
                                SmsEntry(
                                    sender = address,
                                    body = sentBody,
                                    timestamp = timestamp,
                                    isOutgoing = true,
                                    providerId = providerId,
                                )
                            )
                            number = ""
                            body = ""
                        }.onFailure { error ->
                            Toast.makeText(
                                context,
                                error.message ?: "Could not send message",
                                Toast.LENGTH_LONG,
                            ).show()
                        }
                    },
                    enabled = number.isNotBlank() && body.isNotBlank(),
                ) {
                    Icon(Icons.Filled.Send, contentDescription = null)
                    Spacer(Modifier.width(4.dp))
                    Text("Send")
                }
            }
        }
    }
}

@Composable
private fun DefaultSmsBanner(onMakeDefault: () -> Unit, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer,
            contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
        ),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Odikyu isn't your default SMS app yet",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = "Make it the default so all incoming and outgoing SMS go through Odikyu.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            FilledTonalButton(onClick = onMakeDefault) {
                Text("Make default")
            }
        }
    }
}

/** Sends an SMS via SmsManager; returns the body to store on success, or an error for the user. */
private fun sendSms(context: android.content.Context, number: String, body: String): Result<String> {
    if (number.isBlank() || body.isBlank()) {
        return Result.failure(IllegalArgumentException("Enter a number and a message"))
    }
    return try {
        val smsManager = context.getSystemService(SmsManager::class.java)
        smsManager.sendTextMessage(number.trim(), null, body, null, null)
        Result.success(body)
    } catch (e: SecurityException) {
        Result.failure(IllegalStateException("SMS permission was not granted"))
    } catch (e: IllegalArgumentException) {
        Result.failure(IllegalStateException("That number doesn't look valid"))
    }
}

@Composable
private fun MessageBubble(entry: SmsEntry) {
    val time = TIME_FORMAT.format(Instant.ofEpochMilli(entry.timestamp).atZone(ZoneId.systemDefault()))
    val links = remember(entry.body) { Links.extract(entry.body) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
        horizontalAlignment = if (entry.isOutgoing) Alignment.End else Alignment.Start,
    ) {
        Surface(
            color = if (entry.isOutgoing) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceContainerHighest
            },
            contentColor = if (entry.isOutgoing) {
                MaterialTheme.colorScheme.onPrimaryContainer
            } else {
                MaterialTheme.colorScheme.onSurface
            },
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 16.dp,
                bottomStart = if (entry.isOutgoing) 16.dp else 4.dp,
                bottomEnd = if (entry.isOutgoing) 4.dp else 16.dp,
            ),
            tonalElevation = 1.dp,
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = if (entry.isOutgoing) "You" else "From ${entry.sender}",
                        style = MaterialTheme.typography.labelLarge,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = time,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                    )
                }
                Text(
                    text = entry.body,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }

        if (links.isNotEmpty()) {
            LinkWarning(links = links)
        }
    }
}

/** Shown directly below a message that contains a link. */
@Composable
private fun LinkWarning(links: List<String>) {
    Surface(
        color = MaterialTheme.colorScheme.errorContainer,
        contentColor = MaterialTheme.colorScheme.onErrorContainer,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier.padding(top = 4.dp),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(
                imageVector = Icons.Filled.Warning,
                contentDescription = null,
                modifier = Modifier.size(18.dp),
            )
            Column {
                Text(
                    text = "Link detected — possible phishing",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = links.take(3).joinToString("\n") { Links.displayTarget(it) },
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}
