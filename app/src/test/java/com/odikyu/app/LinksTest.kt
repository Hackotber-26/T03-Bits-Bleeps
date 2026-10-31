package com.odikyu.app

import com.odikyu.app.data.Links
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LinksTest {

    @Test
    fun `extracts https url from message`() {
        val links = Links.extract("Your parcel is stuck, pay here https://track-parcel.example.com/pay now")
        assertEquals(listOf("https://track-parcel.example.com/pay"), links)
    }

    @Test
    fun `extracts www and bare domains`() {
        val links = Links.extract("Visit www.somesite.tk or http://192.168.0.1/login")
        assertEquals(2, links.size)
        assertTrue(links[0].startsWith("www."))
    }

    @Test
    fun `ignores plain text without links`() {
        assertTrue(Links.extract("Hello, how are you?").isEmpty())
    }

    @Test
    fun `strips trailing punctuation`() {
        val links = Links.extract("See (https://example.com/page).")
        assertEquals(listOf("https://example.com/page"), links)
    }

    @Test
    fun `display target strips scheme and www`() {
        assertEquals("example.com", Links.displayTarget("https://www.example.com/a"))
        assertEquals("example.com", Links.displayTarget("www.example.com/a"))
    }
}
