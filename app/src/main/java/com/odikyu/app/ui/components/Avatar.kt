package com.odikyu.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.odikyu.app.data.ContactStore
import kotlin.math.abs

private val AVATAR_COLORS = listOf(
    Color(0xFF5B8DEF),
    Color(0xFFF2994A),
    Color(0xFF27AE60),
    Color(0xFFBB6BD9),
    Color(0xFFEB5757),
    Color(0xFF2D9CDB),
    Color(0xFFF2C94C),
    Color(0xFF6FCF97),
)

/**
 * Circular avatar for a phone number: contact photo when available (READ_CONTACTS),
 * otherwise a colored circle with the contact's initial.
 */
@Composable
fun Avatar(
    address: String,
    name: String,
    modifier: Modifier = Modifier,
    size: Dp = 48.dp,
) {
    val context = LocalContext.current
    val photo by produceState<ImageBitmap?>(initialValue = null, key1 = address) {
        value = ContactStore.loadPhoto(context, address)
    }

    val shape = CircleShape
    if (photo != null) {
        androidx.compose.foundation.Image(
            bitmap = photo!!,
            contentDescription = null,
            modifier = modifier
                .size(size)
                .clip(shape),
            contentScale = androidx.compose.ui.layout.ContentScale.Crop,
        )
    } else {
        Box(
            modifier = modifier
                .size(size)
                .clip(shape)
                .background(avatarColor(name, address)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = avatarInitial(name, address),
                color = Color.White,
                fontWeight = FontWeight.SemiBold,
                fontSize = (size.value * 0.38f).sp,
            )
        }
    }
}

private fun avatarInitial(name: String, address: String): String {
    val source = name.ifBlank { address }
    val letter = source.firstOrNull { it.isLetter() } ?: source.firstOrNull { it.isDigit() } ?: '#'
    return letter.uppercaseChar().toString()
}

private fun avatarColor(name: String, address: String): Color {
    val key = name.ifBlank { address }
    return AVATAR_COLORS[abs(key.hashCode()) % AVATAR_COLORS.size]
}
