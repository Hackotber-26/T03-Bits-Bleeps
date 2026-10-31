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
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Divider
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.LifecycleOwner
import com.odikyu.app.data.ContactStore
import com.odikyu.app.data.Conversation
import com.odikyu.app.data.Conversations
import com.odikyu.app.data.Links
import com.odikyu.app.data.SmsEntry
import com.odikyu.app.data.SmsRepository
import com.odikyu.app.data.SmsStore
import com.odikyu.app.ui.components.Avatar
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val REQUIRED_PERMISSIONS = listOf(
    Manifest.permission.SEND_SMS,
    Manifest.permission.RECEIVE_SMS,
    Manifest.permission.READ_CONTACTS,
)

private val TIME_FORMAT = DateTimeFormatter.ofPattern("EEE HH:mm")

@Composable
fun MessagesScreen(modifier: Modifier = Modifier, initialNumber: String? = null) {
    val context = LocalContext.current
    val messages by SmsRepository.messages.collectAsState()
    val contacts by ContactStore.contacts.collectAsState()
    var isDefault by remember { mutableStateOf(SmsStore.isDefaultSmsApp(context)) }
    // Blank = list view; otherwise the open conversation's address.
    var openAddress by rememberSaveable { mutableStateOf(initialNumber.orEmpty()) }

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
                "Odikyu needs SMS and contacts permissions to work fully",
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

    // Resolve contact names/photos for every address we display.
    LaunchedEffect(messages, openAddress) {
        val addresses = (messages.map { it.sender } + openAddress)
            .filter { it.isNotBlank() }
            .distinct()
        ContactStore.resolve(context, addresses)
    }

    if (openAddress.isNotBlank()) {
        BackHandler { openAddress = "" }
        ConversationDetail(
            address = openAddress,
            displayName = contacts[openAddress]?.name ?: openAddress,
            messages = messages.filter {
                Conversations.key(it.sender) == Conversations.key(openAddress)
            },
            isDefault = isDefault,
            onBack = { openAddress = "" },
            modifier = modifier,
        )
    } else {
        ConversationList(
            conversations = remember(messages) { Conversations.group(messages) },
            contacts = contacts,
            isDefault = isDefault,
            onOpen = { openAddress = it },
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
            modifier = modifier,
        )
    }
}

/* ------------------------------------------------------------------ */
/* Conversation list                                                  */
/* ------------------------------------------------------------------ */

@Composable
private fun ConversationList(
    conversations: List<Conversation>,
    contacts: Map<String, com.odikyu.app.data.ContactInfo>,
    isDefault: Boolean,
    onOpen: (String) -> Unit,
    onMakeDefault: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxSize()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, end = 8.dp, top = 16.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Messages",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
            )
            if (conversations.isNotEmpty()) {
                IconButton(onClick = { SmsRepository.clear() }) {
                    Icon(Icons.Filled.Delete, contentDescription = "Clear messages")
                }
            }
        }

        if (!isDefault) {
            DefaultSmsBanner(
                onMakeDefault = onMakeDefault,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }

        if (conversations.isEmpty()) {
            Text(
                text = "No messages yet. Incoming SMS will show up here as conversations.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(16.dp),
            )
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                start = 8.dp, end = 8.dp, top = 4.dp, bottom = 16.dp,
            ),
        ) {
            items(conversations, key = { it.key }) { conversation ->
                ConversationRow(
                    conversation = conversation,
                    name = contacts[conversation.address]?.name,
                    onClick = { onOpen(conversation.address) },
                )
            }
        }
    }
}

@Composable
private fun ConversationRow(
    conversation: Conversation,
    name: String?,
    onClick: () -> Unit,
) {
    val displayName = name ?: conversation.address
    val unread = conversation.unreadCount
    val hasLink = Links.extract(conversation.last.body).isNotEmpty()
    val preview = buildString {
        if (conversation.last.isOutgoing) append("You: ")
        append(conversation.last.body)
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Avatar(
            address = conversation.address,
            name = name.orEmpty(),
            size = 48.dp,
        )
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = displayName,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = if (unread > 0) FontWeight.Bold else FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = true),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    text = relativeTime(conversation.last.timestamp),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                )
            }
            Spacer(Modifier.height(2.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = preview,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (unread > 0) {
                        MaterialTheme.colorScheme.onSurface
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                    fontWeight = if (unread > 0) FontWeight.Medium else FontWeight.Normal,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = true),
                )
                if (hasLink) {
                    Spacer(Modifier.width(6.dp))
                    Icon(
                        imageVector = Icons.Filled.Warning,
                        contentDescription = "Contains a link",
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(16.dp),
                    )
                }
                if (unread > 0) {
                    Spacer(Modifier.width(6.dp))
                    Box(
                        modifier = Modifier
                            .size(20.dp)
                            .clip(CircleShape)
                            .background(MaterialTheme.colorScheme.error),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            text = if (unread > 99) "99+" else unread.toString(),
                            color = MaterialTheme.colorScheme.onError,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* Conversation detail                                                */
/* ------------------------------------------------------------------ */

@Composable
private fun ConversationDetail(
    address: String,
    displayName: String,
    messages: List<SmsEntry>,
    isDefault: Boolean,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var body by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    // Entering the thread clears its unread badge (in memory and in the system store).
    LaunchedEffect(address) {
        SmsRepository.markRead(Conversations.key(address))
        if (SmsStore.isDefaultSmsApp(context)) {
            SmsStore.markThreadRead(context, address)
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
                .padding(horizontal = 4.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, contentDescription = "Back")
            }
            Avatar(address = address, name = displayName, size = 36.dp)
            Spacer(Modifier.width(10.dp))
            Text(
                text = displayName,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Divider()

        if (messages.isEmpty()) {
            Text(
                text = "Say hi — messages in this conversation will appear here.",
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
            contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(messages, key = { it.providerId ?: (it.timestamp * 1000 + it.hashCode()) }) { entry ->
                MessageBubble(entry, showSender = false)
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
                    value = body,
                    onValueChange = { body = it },
                    placeholder = { Text("Message") },
                    maxLines = 4,
                    modifier = Modifier.weight(1f),
                )
                FilledIconButton(
                    onClick = {
                        val text = body
                        val result = sendSms(context, address, text)
                        result.onSuccess { sentBody ->
                            val timestamp = System.currentTimeMillis()
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
                            body = ""
                        }.onFailure { error ->
                            Toast.makeText(
                                context,
                                error.message ?: "Could not send message",
                                Toast.LENGTH_LONG,
                            ).show()
                        }
                    },
                    enabled = body.isNotBlank(),
                ) {
                    Icon(Icons.Filled.Send, contentDescription = "Send")
                }
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* Shared pieces                                                      */
/* ------------------------------------------------------------------ */

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
        return Result.failure(IllegalArgumentException("Enter a message"))
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

private fun relativeTime(timestamp: Long): String {
    val diff = System.currentTimeMillis() - timestamp
    return when {
        diff < 60_000L -> "now"
        diff < 3_600_000L -> "${diff / 60_000L} min ago"
        diff < 86_400_000L -> "${diff / 3_600_000L}h ago"
        diff < 172_800_000L -> "Yesterday"
        diff < 604_800_000L -> Instant.ofEpochMilli(timestamp)
            .atZone(ZoneId.systemDefault())
            .format(DateTimeFormatter.ofPattern("EEE"))
        else -> Instant.ofEpochMilli(timestamp)
            .atZone(ZoneId.systemDefault())
            .format(DateTimeFormatter.ofPattern("d MMM"))
    }
}

@Composable
private fun MessageBubble(entry: SmsEntry, showSender: Boolean = true) {
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
                if (showSender) {
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
                }
                Text(
                    text = entry.body,
                    style = MaterialTheme.typography.bodyMedium,
                )
                if (showSender) {
                    Spacer(Modifier.height(4.dp))
                }
            }
        }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = time,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 2.dp, start = 4.dp, end = 4.dp),
            )
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
