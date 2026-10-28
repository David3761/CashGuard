package com.sst.cashctrl

import android.os.Build
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * The main and only activity of the Android app.
 */
class MainActivity : FlutterFragmentActivity(), MethodChannel.MethodCallHandler {

    /**
     * Called whenever the flutter code calls a method on the native side.
     */
    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "getPlatformVersion" -> {
                result.success("Android ${Build.VERSION.RELEASE}")
            }
        }
    }
}
