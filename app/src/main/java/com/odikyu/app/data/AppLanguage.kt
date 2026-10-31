package com.odikyu.app.data

import android.app.LocaleManager
import android.content.Context
import android.os.Build
import android.os.LocaleList

/** Supported in-app languages, with native display names. */
enum class AppLanguage(val code: String, val nativeName: String, val englishName: String) {
    SYSTEM("", "System default", "Follow system"),
    ENGLISH("en", "English", "English"),
    HINDI("hi", "हिन्दी", "Hindi"),
    BENGALI("bn", "বাংলা", "Bengali"),
    MARATHI("mr", "मराठी", "Marathi"),
    TELUGU("te", "తెలుగు", "Telugu"),
    TAMIL("ta", "தமிழ்", "Tamil");

    companion object {
        fun current(context: Context): AppLanguage {
            val code = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val localeManager = context.getSystemService(LocaleManager::class.java)
                val locales = localeManager?.applicationLocales
                if (locales != null && !locales.isEmpty) locales[0].language else ""
            } else {
                ""
            }
            if (code.isBlank()) return SYSTEM
            return entries.firstOrNull { it.code.equals(code, ignoreCase = true) } ?: SYSTEM
        }

        fun apply(context: Context, language: AppLanguage) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val localeManager = context.getSystemService(LocaleManager::class.java)
                val list = if (language == SYSTEM) {
                    LocaleList.getEmptyLocaleList()
                } else {
                    LocaleList.forLanguageTags(language.code)
                }
                localeManager?.applicationLocales = list
            }
        }
    }
}
