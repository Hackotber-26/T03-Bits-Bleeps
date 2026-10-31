package com.odikyu.app

import com.odikyu.app.data.Classification
import com.odikyu.app.data.MessageCategory
import com.odikyu.app.ui.components.badgeCategory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Pins the two-threshold surfacing rule in [badgeCategory]. */
class CategoryThresholdTest {

    @Test
    fun `low confidence is flagged as suspicious`() {
        // The model README's review cutoff: a shaky guess on a scam is the costly miss.
        val scam = Classification(MessageCategory.TRANSACTIONAL, confidence = 0.49f)
        assertEquals(MessageCategory.UNSAFE, scam.badgeCategory())
    }

    @Test
    fun `mid confidence shows nothing`() {
        // Not suspicious, not confident enough to claim a category — stay quiet.
        listOf(
            MessageCategory.TRANSACTIONAL,
            MessageCategory.PROMOTIONAL,
            MessageCategory.SPAM,
        ).forEach { category ->
            assertNull(Classification(category, confidence = 0.5f).badgeCategory())
            assertNull(Classification(category, confidence = 0.74f).badgeCategory())
        }
    }

    @Test
    fun `confident predictions show their category`() {
        listOf(
            MessageCategory.TRANSACTIONAL,
            MessageCategory.PROMOTIONAL,
            MessageCategory.SPAM,
            MessageCategory.UNSAFE,
        ).forEach { category ->
            assertEquals(
                category,
                Classification(category, confidence = 0.75f).badgeCategory(),
            )
        }
    }

    @Test
    fun `confident personal and unclassified stay unbadged`() {
        assertNull(Classification(MessageCategory.PERSONAL, 0.95f).badgeCategory())
        assertNull(Classification(MessageCategory.UNCLASSIFIED, 0.95f).badgeCategory())
    }

    @Test
    fun `null classification stays unbadged`() {
        val none: Classification? = null
        assertNull(none.badgeCategory())
    }
}
