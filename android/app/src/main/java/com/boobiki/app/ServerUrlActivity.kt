package com.boobiki.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class ServerUrlActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = getSharedPreferences("boobiki", Context.MODE_PRIVATE)
        val saved = prefs.getString("server_url", null)
        if (!saved.isNullOrBlank()) {
            launchMain()
            return
        }

        setContentView(R.layout.activity_server_url)

        val input = findViewById<EditText>(R.id.serverUrlInput)
        val btn = findViewById<Button>(R.id.connectBtn)

        btn.setOnClickListener {
            val url = input.text.toString().trim().trimEnd('/')
            if (url.isEmpty() || !url.startsWith("http")) {
                Toast.makeText(this, "Enter a valid URL (http://...)", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            prefs.edit().putString("server_url", url).apply()
            launchMain()
        }
    }

    private fun launchMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }
}
