package com.odikyu.app.ui.components

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
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
 * The model's README advises treating `max(probs) < 0.5` as suspicious in production
 * (a shaky prediction means the model didn't recognize the message — ambiguity is the
 * signal). Confident PERSONAL/UNCLASSIFIED stay unbadged; everything else shows its icon.
 */
fun Classification?.badgeCategory(): MessageCategory? {
    val verdict = this ?: return null
    if (verdict.confidence < 0.5f) return MessageCategory.UNSAFE
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

/** Small category icon for the bottom-right corner of a conversation card. */
@Composable
fun CategoryIcon(category: MessageCategory, modifier: Modifier = Modifier) {
    val style = styleFor(category) ?: return
    Icon(
        imageVector = style.icon,
        contentDescription = stringResource(style.labelRes),
        tint = style.tint,
        modifier = modifier.size(18.dp),
    )
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