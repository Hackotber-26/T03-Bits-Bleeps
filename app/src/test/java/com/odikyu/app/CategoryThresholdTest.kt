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
        // Uncertainty itself is the warning sign (model README's review rule,
        // cutoff raised from 0.5 to 0.7).
        listOf(0.0f, 0.49f, 0.69f).forEach { conf ->
            val scam = Classification(MessageCategory.TRANSACTIONAL, confidence = conf)
            assertEquals(MessageCategory.UNSAFE, scam.badgeCategory())
        }
    }

    @Test
    fun `mid confidence shows nothing`() {
        // Between the two cutoffs: not suspicious, not confident — stay quiet.
        listOf(
            MessageCategory.TRANSACTIONAL,
            MessageCategory.PROMOTIONAL,
            MessageCategory.SPAM,
        ).forEach { category ->
            assertNull(Classification(category, confidence = 0.7f).badgeCategory())
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
