package com.odikyu.app.data

/** A conversation thread derived from the flat SMS list, grouped by (normalized) address. */
data class Conversation(
    val key: String,
    val address: String,
    val messages: List<SmsEntry>,
    val last: SmsEntry,
    val unreadCount: Int,
)

object Conversations {

    /** Normalizes an address so "+91 98300 12345", "09830012345" etc. group together. */
    fun key(address: String): String {
        val numeric = address.filter { it.isDigit() }
        return when {
            numeric.length >= 10 -> numeric.takeLast(10)
            address.isNotBlank() -> address.trim().lowercase()
            else -> address
        }
    }

    /** Groups messages into conversations, most recent first. */
    fun group(messages: List<SmsEntry>): List<Conversation> =
        messages
            .groupBy { key(it.sender) }
            .map { (groupKey, list) ->
                val sorted = list.sortedBy { it.timestamp }
                val incoming = sorted.lastOrNull { !it.isOutgoing }
                Conversation(
                    key = groupKey,
                    address = incoming?.sender ?: sorted.last().sender,
                    messages = sorted,
                    last = sorted.last(),
                    unreadCount = sorted.count { !it.read && !it.isOutgoing },
                )
            }
            .sortedByDescending { it.last.timestamp }
}
