package com.boobiki.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

class BoobikiService : Service() {

    companion object {
        private const val TAG = "BoobikiService"
        private const val CHANNEL_SERVICE = "boobiki_service"
        private const val CHANNEL_NOTIFY = "boobiki_notifications"
        private const val SERVICE_NOTIFICATION_ID = 1
        private const val BASE_RECONNECT_MS = 2000L
        private const val MAX_RECONNECT_MS = 30000L
    }

    private var ws: WebSocket? = null
    private var reconnectDelay = BASE_RECONNECT_MS
    private var wakeLock: PowerManager.WakeLock? = null
    private var activityVisible = false
    private var reconnectPending = false
    private val handler = android.os.Handler(android.os.Looper.getMainLooper())

    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(30, TimeUnit.SECONDS)
        .build()

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
        startForeground(SERVICE_NOTIFICATION_ID, buildServiceNotification("Waiting..."))
        acquireWakeLock()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            "ACTIVITY_VISIBLE" -> {
                activityVisible = true
                // WebView JS will handle WS — disconnect ours
                cancelReconnect()
                ws?.close(1000, "Activity visible")
                ws = null
                updateServiceNotification("App is open")
            }
            "ACTIVITY_HIDDEN" -> {
                activityVisible = false
                // Take over WS for background notifications
                connectWebSocket()
            }
            else -> {
                // Initial start — activity is about to show, so wait
                activityVisible = true
                updateServiceNotification("App is open")
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        cancelReconnect()
        ws?.close(1000, "Service stopped")
        wakeLock?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    private fun acquireWakeLock() {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "boobiki:ws"
        ).apply { acquire() }
    }

    private fun getServerUrl(): String? {
        return getSharedPreferences("boobiki", Context.MODE_PRIVATE)
            .getString("server_url", null)
    }

    private fun getStoredDeviceId(): String {
        val prefs = getSharedPreferences("boobiki", Context.MODE_PRIVATE)
        var id = prefs.getString("device_id", null)
        if (id == null) {
            id = UUID.randomUUID().toString()
            prefs.edit().putString("device_id", id).apply()
        }
        return id
    }

    private fun getDeviceName(): String {
        val prefs = getSharedPreferences("boobiki", Context.MODE_PRIVATE)
        var name = prefs.getString("device_name", null)
        if (name == null) {
            name = "${Build.MANUFACTURER} ${Build.MODEL}".trim()
            prefs.edit().putString("device_name", name).apply()
        }
        return name
    }

    private fun connectWebSocket() {
        if (activityVisible) return  // WebView handles WS when visible

        val baseUrl = getServerUrl() ?: return
        val wsUrl = baseUrl.replace("http://", "ws://").replace("https://", "wss://") + "/ws"

        Log.i(TAG, "Connecting to $wsUrl")
        updateServiceNotification("Connecting...")

        val request = Request.Builder().url(wsUrl).build()
        ws = client.newWebSocket(request, object : WebSocketListener() {

            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "WS connected")
                reconnectDelay = BASE_RECONNECT_MS

                val reg = JSONObject().apply {
                    put("type", "register")
                    put("name", getDeviceName())
                    put("device_id", getStoredDeviceId())
                }
                webSocket.send(reg.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val msg = JSONObject(text)
                    when (msg.optString("type")) {
                        "registered" -> {
                            val deviceId = msg.getString("device_id")
                            getSharedPreferences("boobiki", Context.MODE_PRIVATE)
                                .edit().putString("device_id", deviceId).apply()
                            updateServiceNotification("Connected")
                            Log.i(TAG, "Registered as $deviceId")
                        }
                        "notification" -> {
                            val body = msg.optString("text", "")
                            val sender = msg.optString("sender", "")
                            if (body.isNotEmpty()) {
                                showNotification(sender, body)
                            }
                        }
                        "pong" -> { /* heartbeat */ }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Failed to parse WS message", e)
                }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "WS failed: ${t.message}")
                if (!activityVisible) {
                    updateServiceNotification("Disconnected — retrying...")
                    scheduleReconnect()
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "WS closed: $code")
                if (!activityVisible) {
                    updateServiceNotification("Disconnected — retrying...")
                    scheduleReconnect()
                }
            }
        })
    }

    private fun scheduleReconnect() {
        if (activityVisible) return
        cancelReconnect()
        reconnectPending = true
        handler.postDelayed({
            reconnectPending = false
            connectWebSocket()
        }, reconnectDelay)
        reconnectDelay = (reconnectDelay * 2).coerceAtMost(MAX_RECONNECT_MS)
    }

    private fun cancelReconnect() {
        if (reconnectPending) {
            handler.removeCallbacksAndMessages(null)
            reconnectPending = false
        }
        reconnectDelay = BASE_RECONNECT_MS
    }

    // ── Notifications ───────────────────────────────────────

    private fun createNotificationChannels() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_SERVICE, "Connection", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Persistent connection to Boobiki server"
                setShowBadge(false)
            }
        )

        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_NOTIFY, "Notifications", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Push notifications from Boobiki"
                enableVibration(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
        )
    }

    private fun buildServiceNotification(status: String): Notification {
        val openIntent = Intent(this, MainActivity::class.java)
        val pending = PendingIntent.getActivity(
            this, 0, openIntent, PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_SERVICE)
            .setContentTitle("Boobiki")
            .setContentText(status)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .setContentIntent(pending)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun updateServiceNotification(status: String) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(SERVICE_NOTIFICATION_ID, buildServiceNotification(status))
    }

    private fun showNotification(sender: String, text: String) {
        val title = if (sender.isNotEmpty()) "Boobiki — $sender" else "Boobiki"
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pending = PendingIntent.getActivity(
            this, System.currentTimeMillis().toInt(), openIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_NOTIFY)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_dialog_email)
            .setAutoCancel(true)
            .setContentIntent(pending)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .build()

        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(System.currentTimeMillis().toInt(), notification)
    }
}
