package com.odikyu.app.ui.components

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.odikyu.app.data.FaviconStore

/**
 * Small rounded website icon loaded from Google's favicon service.
 * Shows a neutral placeholder of the same size while loading or when unavailable.
 */
@Composable
fun Favicon(
    domain: String,
    modifier: Modifier = Modifier,
    size: Dp = 16.dp,
) {
    val icon by produceState<ImageBitmap?>(initialValue = null, key1 = domain) {
        value = FaviconStore.load(domain)
    }

    if (icon != null) {
        Image(
            bitmap = icon!!,
            contentDescription = domain,
            modifier = modifier
                .size(size)
                .clip(RoundedCornerShape(3.dp)),
        )
    } else {
        Box(
            modifier = modifier
                .size(size)
                .clip(RoundedCornerShape(3.dp))
                .background(MaterialTheme.colorScheme.surfaceContainerHighest),
        )
    }
}
