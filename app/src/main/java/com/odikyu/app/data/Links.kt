package com.odikyu.app.data

/** Extracts URLs from an SMS body so the UI can warn before a link is tapped. */
object Links {

    private val LINK_REGEX = Regex("""(?i)(https?://|www\.)[^\s<>()"'{}\[\]]+""")

    private val TRAILING_PUNCTUATION = charArrayOf('.', ',', ';', ':', '!', '?', ')', '\'', '"')

    fun extract(body: String): List<String> =
        LINK_REGEX.findAll(body)
            .map { match ->
                match.value.trimEnd { it in TRAILING_PUNCTUATION }
            }
            .filter { it.length > 7 } // ignore bare "http://x"
            .distinct()
            .toList()

    /** Best-effort display name for a link, e.g. "login-verify-odikyu.tk". */
    fun displayTarget(link: String): String = runCatching {
        if (link.startsWith("http://", true) || link.startsWith("https://", true)) {
            java.net.URL(link).host.removePrefix("www.")
        } else {
            link.substringBefore("/").substringAfter("www.")
        }
    }.getOrDefault(link)
}
