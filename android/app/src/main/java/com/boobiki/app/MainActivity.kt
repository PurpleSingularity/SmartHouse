package com.boobiki.app

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        requestNotificationPermission()

        val prefs = getSharedPreferences("boobiki", Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", null)
        if (serverUrl.isNullOrBlank()) {
            startActivity(Intent(this, ServerUrlActivity::class.java))
            finish()
            return
        }

        // Start the foreground service (it will wait until activity goes to background)
        ContextCompat.startForegroundService(this, Intent(this, BoobikiService::class.java))

        webView = findViewById(R.id.webView)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            userAgentString = "$userAgentString BoobikiApp"
        }
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) = false

            override fun onPageFinished(view: WebView, url: String?) {
                super.onPageFinished(view, url)
                // Sync device ID from native SharedPreferences → WebView localStorage
                // so both the WebView JS and the service use the same identity
                val deviceId = prefs.getString("device_id", null) ?: return
                val deviceName = prefs.getString("device_name", null) ?: return
                view.evaluateJavascript(
                    "localStorage.setItem('boobiki_device_id','$deviceId');" +
                    "localStorage.setItem('boobiki_device_name','$deviceName');",
                    null
                )
            }
        }
        webView.webChromeClient = WebChromeClient()
        webView.loadUrl(serverUrl)
    }

    override fun onResume() {
        super.onResume()
        // WebView is visible — tell service to yield WS connection
        sendServiceCommand("ACTIVITY_VISIBLE")
    }

    override fun onPause() {
        super.onPause()
        // WebView going away — tell service to take over WS
        sendServiceCommand("ACTIVITY_HIDDEN")
    }

    private fun sendServiceCommand(action: String) {
        val intent = Intent(this, BoobikiService::class.java).apply { this.action = action }
        startService(intent)
    }

    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            AlertDialog.Builder(this)
                .setTitle("Boobiki")
                .setItems(arrayOf("Change server", "Exit")) { _, which ->
                    when (which) {
                        0 -> {
                            getSharedPreferences("boobiki", Context.MODE_PRIVATE)
                                .edit().remove("server_url").apply()
                            startActivity(Intent(this, ServerUrlActivity::class.java))
                            finish()
                        }
                        1 -> {
                            stopService(Intent(this, BoobikiService::class.java))
                            finishAffinity()
                        }
                    }
                }
                .show()
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                    1001
                )
            }
        }
    }
}
