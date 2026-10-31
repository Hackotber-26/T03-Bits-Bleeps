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
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
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
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.LifecycleOwner
import com.odikyu.app.R
import com.odikyu.app.data.ContactStore
import com.odikyu.app.data.Conversation
import com.odikyu.app.data.Conversations
import com.odikyu.app.data.Classification
import com.odikyu.app.data.Links
import com.odikyu.app.data.MessageCategory
import com.odikyu.app.data.MessageClassifier
import com.odikyu.app.data.SmsEntry
import com.odikyu.app.data.SmsRepository
import com.odikyu.app.data.SmsStore
import com.odikyu.app.ui.components.Avatar
import com.odikyu.app.ui.components.CategoryBadge
import com.odikyu.app.ui.components.CategoryCornerIcon
import com.odikyu.app.ui.components.Favicon
import com.odikyu.app.ui.components.FaviconAvatar
import com.odikyu.app.ui.components.badgeCategory
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private val REQUIRED_PERMISSIONS = listOf(
    Manifest.permission.SEND_SMS,
    Manifest.permission.RECEIVE_SMS,
    Manifest.permission.READ_CONTACTS,
)

private val TIME_FORMAT_PATTERN = "EEE HH:mm"

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
                context.getString(R.string.toast_permissions),
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

    val conversations = remember(messages) { Conversations.group(messages) }

    // Classify each conversation's latest message off the main thread; keyed by conversation
    // key so rows just look up their verdict. Cache in the classifier makes re-runs cheap.
    val classifications by produceState<Map<String, Classification>>(emptyMap(), conversations) {
        value = withContext(Dispatchers.IO) {
            conversations.mapNotNull { conversation ->
                MessageClassifier.classify(context, conversation.last.body)
                    ?.let { conversation.key to it }
            }.toMap()
        }
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
            conversations = conversations,
            classifications = classifications,
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
                        context.getString(R.string.toast_role_failed, e.message),
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
    classifications: Map<String, Classification>,
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
                text = stringResource(R.string.messages),
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
            )
        }

        if (!isDefault) {
            DefaultSmsBanner(
                onMakeDefault = onMakeDefault,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }

        if (conversations.isEmpty()) {
            Text(
                text = stringResource(R.string.empty_conversations),
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
                    classification = classifications[conversation.key],
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
    classification: Classification?,
    onClick: () -> Unit,
) {
    val displayName = name ?: conversation.address
    val unread = conversation.unreadCount
    val youPrefix = stringResource(R.string.you_prefix)
    val category = classification.badgeCategory()
    val lastLinkDomain = remember(conversation.last.body) {
        Links.extract(conversation.last.body).firstOrNull()?.let(Links::displayTarget)
    }
    val preview = buildString {
        if (conversation.last.isOutgoing) append(youPrefix)
        append(conversation.last.body)
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box {
            if (lastLinkDomain != null) {
                FaviconAvatar(domain = lastLinkDomain, size = 48.dp)
            } else {
                Avatar(
                    address = conversation.address,
                    name = name.orEmpty(),
                    size = 48.dp,
                )
            }
            // Category pin at the card's top-left corner, ringed so it reads on any avatar.
            if (category != null) {
                CategoryCornerIcon(
                    category = category,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .offset(x = (-4).dp, y = (-4).dp),
                )
            }
        }
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
                if (unread > 0) {
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
    // Open directly at the newest message — no scroll animation on entry.
    val listState = rememberLazyListState(
        initialFirstVisibleItemIndex = (messages.size - 1).coerceAtLeast(0),
    )

    // Entering the thread clears its unread badge (in memory and in the system store).
    LaunchedEffect(address) {
        SmsRepository.markRead(Conversations.key(address))
        if (SmsStore.isDefaultSmsApp(context)) {
            SmsStore.markThreadRead(context, address)
        }
    }

    // Keep it pinned to the newest message as messages arrive (instantly, not animated).
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.scrollToItem(messages.lastIndex)
        }
    }

    Column(
        modifier = modifier.fillMaxSize(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 4.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, contentDescription = stringResource(R.string.cd_back))
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
                text = stringResource(R.string.empty_thread),
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
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                // Bottom-aligns so the send button tracks the field as it grows to 4 lines.
                verticalAlignment = Alignment.Bottom,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Surface(
                    shape = RoundedCornerShape(24.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerHigh,
                    modifier = Modifier.weight(1f),
                ) {
                    OutlinedTextField(
                        value = body,
                        onValueChange = { body = it },
                        placeholder = { Text(stringResource(R.string.message_hint)) },
                        maxLines = 4,
                        modifier = Modifier.fillMaxWidth(),
                        colors = TextFieldDefaults.colors(
                            focusedContainerColor = Color.Transparent,
                            unfocusedContainerColor = Color.Transparent,
                            disabledContainerColor = Color.Transparent,
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent,
                            disabledIndicatorColor = Color.Transparent,
                            cursorColor = MaterialTheme.colorScheme.primary,
                        ),
                    )
                }
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
                                error.message ?: context.getString(R.string.err_send_failed),
                                Toast.LENGTH_LONG,
                            ).show()
                        }
                    },
                    enabled = body.isNotBlank(),
                    modifier = Modifier.size(48.dp),
                ) {
                    Icon(Icons.Filled.Send, contentDescription = stringResource(R.string.cd_send))
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
                    text = stringResource(R.string.default_sms_title),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    text = stringResource(R.string.default_sms_body),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            FilledTonalButton(onClick = onMakeDefault) {
                Text(stringResource(R.string.default_sms_action))
            }
        }
    }
}

/** Sends an SMS via SmsManager; returns the body to store on success, or an error for the user. */
private fun sendSms(context: android.content.Context, number: String, body: String): Result<String> {
    if (number.isBlank() || body.isBlank()) {
        return Result.failure(IllegalArgumentException(context.getString(R.string.err_enter_message)))
    }
    return try {
        val smsManager = context.getSystemService(SmsManager::class.java)
        smsManager.sendTextMessage(number.trim(), null, body, null, null)
        Result.success(body)
    } catch (e: SecurityException) {
        Result.failure(IllegalStateException(context.getString(R.string.err_no_permission)))
    } catch (e: IllegalArgumentException) {
        Result.failure(IllegalStateException(context.getString(R.string.err_bad_number)))
    }
}

@Composable
private fun relativeTime(timestamp: Long): String {
    val diff = System.currentTimeMillis() - timestamp
    return when {
        diff < 60_000L -> stringResource(R.string.time_now)
        diff < 3_600_000L -> stringResource(R.string.time_minutes_ago, diff / 60_000L)
        diff < 86_400_000L -> stringResource(R.string.time_hours_ago, diff / 3_600_000L)
        diff < 172_800_000L -> stringResource(R.string.time_yesterday)
        else -> localizedDate(timestamp, if (diff < 604_800_000L) "EEE" else "d MMM")
    }
}

/** Date formatted with the user's locale so weekday/month names come out translated. */
@Composable
private fun localizedDate(timestamp: Long, pattern: String): String {
    val locale = LocalConfiguration.current.locales[0]
    return remember(timestamp, locale, pattern) {
        DateTimeFormatter.ofPattern(pattern, locale)
            .format(Instant.ofEpochMilli(timestamp).atZone(ZoneId.systemDefault()))
    }
}

@Composable
private fun MessageBubble(entry: SmsEntry, showSender: Boolean = true) {
    val context = LocalContext.current
    val locale = LocalConfiguration.current.locales[0]
    val time = remember(entry.timestamp, locale) {
        DateTimeFormatter.ofPattern(TIME_FORMAT_PATTERN, locale)
            .format(Instant.ofEpochMilli(entry.timestamp).atZone(ZoneId.systemDefault()))
    }
    val links = remember(entry.body) { Links.extract(entry.body) }
    // Only incoming messages get classified — outgoing ones are your own words.
    val classification by produceState<Classification?>(initialValue = null, entry.body) {
        if (!entry.isOutgoing) {
            value = withContext(Dispatchers.IO) {
                MessageClassifier.classify(context, entry.body)
            }
        }
    }
    val category = classification.badgeCategory()
    val isSuspicious = category == MessageCategory.UNSAFE

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
        horizontalAlignment = if (entry.isOutgoing) Alignment.End else Alignment.Start,
    ) {
        Surface(
            color = when {
                entry.isOutgoing -> MaterialTheme.colorScheme.primaryContainer
                // Suspicious messages wear the same warning red as the Protection screen.
                isSuspicious -> MaterialTheme.colorScheme.errorContainer
                else -> MaterialTheme.colorScheme.surfaceContainerHighest
            },
            contentColor = when {
                entry.isOutgoing -> MaterialTheme.colorScheme.onPrimaryContainer
                isSuspicious -> MaterialTheme.colorScheme.onErrorContainer
                else -> MaterialTheme.colorScheme.onSurface
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
                            text = if (entry.isOutgoing) {
                                stringResource(R.string.you_label)
                            } else {
                                stringResource(R.string.from_label, entry.sender)
                            },
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
                if (links.isNotEmpty()) {
                    LinkedBody(body = entry.body, links = links)
                } else {
                    Text(
                        text = entry.body,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                // Classification lives inside the bubble, stamped at its bottom-right.
                if (category != null && !isSuspicious) {
                    Spacer(Modifier.height(6.dp))
                    CategoryBadge(
                        category = category,
                        modifier = Modifier.align(Alignment.End),
                    )
                }
                Spacer(Modifier.height(4.dp))
            }
        }

        Text(
            text = time,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 2.dp, start = 4.dp, end = 4.dp),
        )
    }
}

/** Opens a URL from a message; everything is filtered through the browser. */
private fun openLink(context: android.content.Context, url: String) {
    val target = if (url.startsWith("http://", true) || url.startsWith("https://", true)) {
        url
    } else {
        "https://$url"
    }
    runCatching {
        context.startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(target)))
    }
}

/**
 * Message body with every link rendered as an inline, tappable chip (favicon + domain)
 * flowing on the same lines as the surrounding words. Plain words and chips are laid out
 * like a paragraph: wraps happen at word boundaries, a chip never splits mid-domain.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LinkedBody(body: String, links: List<String>) {
    val context = LocalContext.current
    val segments = remember(body, links) { splitAroundLinks(body, links) }
    val bodyStyle = MaterialTheme.typography.bodyMedium
    val chipStyle = MaterialTheme.typography.labelMedium
    val chipBackground = MaterialTheme.colorScheme.surfaceContainerHighest
    val chipForeground = MaterialTheme.colorScheme.primary

    FlowRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        segments.forEach { segment ->
            when (segment) {
                is BodySeg.Text -> segment.value.split(WORD_SPLIT).forEach { word ->
                    if (word.isNotEmpty()) {
                        Text(
                            text = word,
                            style = bodyStyle,
                            modifier = Modifier.align(Alignment.CenterVertically),
                        )
                    }
                }

                is BodySeg.Link -> LinkChips(
                    url = segment.url,
                    style = chipStyle,
                    background = chipBackground,
                    foreground = chipForeground,
                    modifier = Modifier.align(Alignment.CenterVertically),
                    onClick = { openLink(context, segment.url) },
                )
            }
        }
    }
}

private val WORD_SPLIT = Regex("\\s+")

/** One clickable link chip: favicon + domain + ↗, sized to its content. */
@Composable
private fun LinkChips(
    url: String,
    style: androidx.compose.ui.text.TextStyle,
    background: androidx.compose.ui.graphics.Color,
    foreground: androidx.compose.ui.graphics.Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val domain = Links.displayTarget(url)
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(
            modifier = Modifier
                .height(24.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(background)
                .clickable(onClick = onClick)
                .padding(horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            Favicon(domain = domain, size = 14.dp)
            Text(
                text = domain,
                style = style,
                color = foreground,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                // Cap the chip at the bubble width without forcing it to fill.
                modifier = Modifier.weight(1f, fill = false),
            )
            Text(
                text = "↗",
                style = style,
                color = foreground,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

private sealed interface BodySeg {
    data class Text(val value: String) : BodySeg
    data class Link(val url: String) : BodySeg
}

/** Splits a body around its links, preserving every other character (incl. newlines). */
private fun splitAroundLinks(body: String, links: List<String>): List<BodySeg> {
    if (links.isEmpty()) return listOf(BodySeg.Text(body))
    val out = mutableListOf<BodySeg>()
    var cursor = 0
    while (cursor < body.length) {
        var hitIndex = -1
        var hitLink = ""
        for (link in links) {
            val i = body.indexOf(link, cursor)
            if (i >= 0 && (hitIndex < 0 || i < hitIndex)) {
                hitIndex = i
                hitLink = link
            }
        }
        if (hitIndex < 0) {
            out.add(BodySeg.Text(body.substring(cursor)))
            break
        }
        if (hitIndex > cursor) out.add(BodySeg.Text(body.substring(cursor, hitIndex)))
        out.add(BodySeg.Link(hitLink))
        cursor = hitIndex + hitLink.length
    }
    return out.filter { it !is BodySeg.Text || it.value.isNotEmpty() }
}
