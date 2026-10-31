package com.odikyu.app.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/** A single SMS, either received by [com.odikyu.app.receiver.SmsReceiver] or sent from the app. */
data class SmsEntry(
    val sender: String,
    val body: String,
    val timestamp: Long,
    val isOutgoing: Boolean,
)

/** In-memory inbox shared between the receiver and the UI. */
object SmsRepository {

    private const val MAX_ENTRIES = 200

    private val _messages = MutableStateFlow<List<SmsEntry>>(emptyList())
    val messages: StateFlow<List<SmsEntry>> = _messages.asStateFlow()

    fun add(entry: SmsEntry) {
        _messages.update { current -> (current + entry).takeLast(MAX_ENTRIES) }
    }

    fun clear() {
        _messages.update { emptyList() }
    }
}
