package com.odikyu.app.ui.navigation

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.WindowInsets
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

    Scaffold(modifier = modifier) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
        ) {
            Column(modifier = Modifier.weight(1f)) {
                when (currentTab) {
                    OdikyuTab.Messages -> MessagesScreen(initialNumber = prefillNumber)
                    OdikyuTab.Protection -> DnsScreen()
                    OdikyuTab.Settings -> SettingsScreen()
                }
            }

            NavigationBar(
                containerColor = MaterialTheme.colorScheme.background,
                // The Scaffold's innerPadding already lifts content above the system nav bar;
                // letting the bar add its own inset again would leave a dead gap below it.
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
