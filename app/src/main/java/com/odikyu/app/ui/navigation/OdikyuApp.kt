package com.odikyu.app.ui.navigation

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.union
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.outlined.Email
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import com.odikyu.app.ui.screens.DnsScreen
import com.odikyu.app.ui.screens.MessagesScreen
import com.odikyu.app.ui.screens.SettingsScreen

enum class OdikyuTab(
    val titleRes: Int,
    val filledIcon: ImageVector,
    val outlinedIcon: ImageVector,
) {
    Messages(com.odikyu.app.R.string.messages, Icons.Filled.Email, Icons.Outlined.Email),
    Protection(com.odikyu.app.R.string.protection, Icons.Filled.Lock, Icons.Outlined.Lock),
    Settings(com.odikyu.app.R.string.settings, Icons.Filled.Settings, Icons.Outlined.Settings),
}

@Composable
fun OdikyuApp(
    modifier: Modifier = Modifier,
    prefillNumber: String? = null,
) {
    var currentTab by rememberSaveable { mutableStateOf(OdikyuTab.Messages) }
    val density = LocalDensity.current
    // Hide the tab bar while typing so the composer sits flush on the keyboard.
    val imeVisible = WindowInsets.ime.getBottom(density) > 0

    Scaffold(
        modifier = modifier,
        // Insets are applied manually below: bottom = max(navigationBars, ime), so no
        // dead gap can open between the composer and the keyboard (adjustResize does
        // nothing under edge-to-edge; imePadding alone would double-count the nav bar).
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
    ) { _ ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.statusBars.only(WindowInsetsSides.Top))
                .windowInsetsPadding(
                    WindowInsets.navigationBars
                        .union(WindowInsets.ime)
                        .only(WindowInsetsSides.Bottom),
                ),
        ) {
            Column(modifier = Modifier.weight(1f)) {
                when (currentTab) {
                    OdikyuTab.Messages -> MessagesScreen(initialNumber = prefillNumber)
                    OdikyuTab.Protection -> DnsScreen()
                    OdikyuTab.Settings -> SettingsScreen()
                }
            }

            if (!imeVisible) {
                NavigationBar(
                    containerColor = MaterialTheme.colorScheme.background,
                    // Top-level insets are applied on the root column above; letting the
                    // bar add its own again would leave a dead gap below it.
                    windowInsets = WindowInsets(0, 0, 0, 0),
                ) {
                    OdikyuTab.entries.forEach { tab ->
                        val title = stringResource(tab.titleRes)
                        NavigationBarItem(
                            selected = currentTab == tab,
                            onClick = { currentTab = tab },
                            icon = {
                                Icon(
                                    imageVector = if (currentTab == tab) tab.filledIcon else tab.outlinedIcon,
                                    contentDescription = title,
                                )
                            },
                            label = { Text(title) },
                        )
                    }
                }
            }
        }
    }
}
