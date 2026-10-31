package com.odikyu.app

import com.odikyu.app.data.Classification
import com.odikyu.app.data.MessageCategory
import com.odikyu.app.ui.components.badgeCategory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Pins the surfacing rule in [badgeCategory]. Confidence values are real outputs
 * of the shipped model on real messages from the test device.
 */
class CategoryThresholdTest {

    @Test
    fun `model pointing at unsafe is flagged as suspicious`() {
        // Known scam texts: Banbaloo prize-scam -> UNSAFE 0.54,
        // Aadhaar-KYC phish -> UNSAFE 0.45.
        listOf(0.4f, 0.45f, 0.54f, 0.9f).forEach { conf ->
            assertEquals(
                MessageCategory.UNSAFE,
                Classification(MessageCategory.UNSAFE, conf).badgeCategory(),
            )
        }
    }

    @Test
    fun `a torn near-uniform unsafe guess stays quiet`() {
        assertNull(Classification(MessageCategory.UNSAFE, 0.35f).badgeCategory())
    }

    @Test
    fun `ambiguity alone is not suspicion`() {
        // Gov service SMS -> TRANSACTIONAL 0.698, Jio offer -> PROMOTIONAL 0.506,
        // BigBasket promo -> TRANSACTIONAL 0.49: recognized-but-uncertain = blank.
        listOf(
            Classification(MessageCategory.TRANSACTIONAL, 0.698f),
            Classification(MessageCategory.PROMOTIONAL, 0.506f),
            Classification(MessageCategory.TRANSACTIONAL, 0.49f),
            Classification(MessageCategory.SPAM, 0.6f),
        ).forEach { assertNull(it.badgeCategory()) }
    }

    @Test
    fun `confident predictions show their category`() {
        listOf(
            MessageCategory.TRANSACTIONAL,
            MessageCategory.PROMOTIONAL,
            MessageCategory.SPAM,
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
        // "hi harshit" -> UNCLASSIFIED 0.74 on device.
        assertNull(Classification(MessageCategory.UNCLASSIFIED, 0.74f).badgeCategory())
    }

    @Test
    fun `null classification stays unbadged`() {
        val none: Classification? = null
        assertNull(none.badgeCategory())
    }
}
