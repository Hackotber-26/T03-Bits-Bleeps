package com.odikyu.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.odikyu.app.data.SmsEntry
import com.odikyu.app.data.SmsRepository
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val REQUIRED_PERMISSIONS = listOf(
    Manifest.permission.SEND_SMS,
    Manifest.permission.RECEIVE_SMS,
)

private val TIME_FORMAT = DateTimeFormatter.ofPattern("EEE HH:mm")

@Composable
fun MessagesScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val messages by SmsRepository.messages.collectAsState()
    var number by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

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

    LaunchedEffect(Unit) {
        val missing = REQUIRED_PERMISSIONS.filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            permissionLauncher.launch(missing.toTypedArray())
        }
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
            items(messages, key = { it.timestamp to it.hashCode() }) { entry ->
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
                        result.onSuccess { entry ->
                            SmsRepository.add(entry)
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

/** Sends an SMS; returns the local outgoing entry on success, or an error to show the user. */
private fun sendSms(context: android.content.Context, number: String, body: String): Result<SmsEntry> {
    if (number.isBlank() || body.isBlank()) {
        return Result.failure(IllegalArgumentException("Enter a number and a message"))
    }
    return try {
        val smsManager = context.getSystemService(SmsManager::class.java)
        smsManager.sendTextMessage(number.trim(), null, body, null, null)
        Result.success(
            SmsEntry(
                sender = number.trim(),
                body = body,
                timestamp = System.currentTimeMillis(),
                isOutgoing = true,
            )
        )
    } catch (e: SecurityException) {
        Result.failure(IllegalStateException("SMS permission was not granted"))
    } catch (e: IllegalArgumentException) {
        Result.failure(IllegalStateException("That number doesn't look valid"))
    }
}

@Composable
private fun MessageBubble(entry: SmsEntry) {
    val time = TIME_FORMAT.format(Instant.ofEpochMilli(entry.timestamp).atZone(ZoneId.systemDefault()))
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
        horizontalArrangement = if (entry.isOutgoing) Arrangement.End else Arrangement.Start,
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
    }
}

