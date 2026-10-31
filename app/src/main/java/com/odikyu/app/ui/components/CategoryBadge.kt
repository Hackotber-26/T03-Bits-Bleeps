package com.odikyu.app.ui.components

import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.odikyu.app.R
import com.odikyu.app.data.Classification
import com.odikyu.app.data.MessageCategory

/**
 * The verdict worth surfacing on a card — null for a plain, unremarkable message.
 *
 * Two thresholds, deliberately different:
 * - Below [SUSPICIOUS_BELOW] the model is essentially guessing (its README says to treat
 *   `max(probs) < 0.5` as review-worthy) — that ambiguity *is* the signal, so it surfaces
 *   as Suspicious: a shaky guess on a scam is the failure mode we care about.
 * - Normal categories only show when the model is clearly sure of them
 *   ([CONFIDENT_ABOUT]). In between: nothing at all — no half-hearted classifications.
 */
private const val SUSPICIOUS_BELOW = 0.5f
private const val CONFIDENT_ABOUT = 0.75f

fun Classification?.badgeCategory(): MessageCategory? {
    val verdict = this ?: return null
    if (verdict.confidence < SUSPICIOUS_BELOW) return MessageCategory.UNSAFE
    if (verdict.confidence < CONFIDENT_ABOUT) return null
    return when (verdict.category) {
        MessageCategory.PERSONAL,
        MessageCategory.UNCLASSIFIED,
        -> null

        else -> verdict.category
    }
}

/** Icon + accent color for a category; null for PERSONAL/UNCLASSIFIED (never badged). */
private data class CategoryStyle(
    @StringRes val labelRes: Int,
    val icon: ImageVector,
    val tint: Color,
)

@Composable
private fun styleFor(category: MessageCategory): CategoryStyle? {
    val scheme = MaterialTheme.colorScheme
    return when (category) {
        MessageCategory.PERSONAL,
        MessageCategory.UNCLASSIFIED,
        -> null

        // Red warning glyph only — no background wash on the message index.
        MessageCategory.UNSAFE ->
            CategoryStyle(R.string.cat_unsafe, Icons.Filled.Warning, scheme.error)
        MessageCategory.TRANSACTIONAL ->
            CategoryStyle(R.string.cat_transactional, Icons.Filled.CheckCircle, scheme.tertiary)
        MessageCategory.PROMOTIONAL ->
            CategoryStyle(R.string.cat_promotional, Icons.Filled.Star, scheme.secondary)
        MessageCategory.SPAM ->
            CategoryStyle(R.string.cat_spam, Icons.Filled.Delete, scheme.onSurfaceVariant)
    }
}

/** Small round badge pinned to the top-left corner of an avatar/card. */
@Composable
fun CategoryCornerIcon(category: MessageCategory, modifier: Modifier = Modifier) {
    val style = styleFor(category) ?: return
    Box(
        modifier = modifier
            .size(20.dp)
            .clip(CircleShape)
            .background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = style.icon,
            contentDescription = stringResource(style.labelRes),
            tint = style.tint,
            modifier = Modifier.size(14.dp),
        )
    }
}

/** Compact colored pill identifying what kind of message this is (thread view). */
@Composable
fun CategoryBadge(category: MessageCategory, modifier: Modifier = Modifier) {
    val style = styleFor(category) ?: return
    Surface(
        color = style.tint.copy(alpha = 0.18f),
        contentColor = style.tint,
        shape = RoundedCornerShape(7.dp),
        modifier = modifier,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (category == MessageCategory.UNSAFE) {
                Icon(
                    imageVector = Icons.Filled.Warning,
                    contentDescription = null,
                    modifier = Modifier.size(13.dp),
                )
                Spacer(Modifier.width(5.dp))
            }
            Text(
                text = stringResource(style.labelRes),
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
            )
        }
    }
}