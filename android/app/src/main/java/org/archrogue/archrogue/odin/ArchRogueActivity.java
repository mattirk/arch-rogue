package org.archrogue.archrogue.odin;

import android.annotation.TargetApi;
import android.app.NativeActivity;
import android.os.Build;
import android.os.Bundle;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;

/** NativeActivity shell that forwards both legacy and gesture Back to Odin. */
public final class ArchRogueActivity extends NativeActivity {
    static {
        // Associate libmain with this app class loader so conventional JNI symbol
        // lookup can resolve nativeOnBackPressed. NativeActivity's framework load
        // still owns ANativeActivity_onCreate; the audited library has no DT_INIT.
        System.loadLibrary("main");
    }

    private Object backCallback;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            backCallback = Api33BackDispatcher.register(
                this,
                ArchRogueActivity::nativeOnBackPressed
            );
        }
    }

    @Override
    protected void onDestroy() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && backCallback != null) {
            Api33BackDispatcher.unregister(this, backCallback);
            backCallback = null;
        }
        super.onDestroy();
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        nativeOnBackPressed();
    }

    private static native void nativeOnBackPressed();

    @TargetApi(Build.VERSION_CODES.TIRAMISU)
    private static final class Api33BackDispatcher {
        private Api33BackDispatcher() {}

        static Object register(ArchRogueActivity activity, Runnable action) {
            OnBackInvokedCallback callback = action::run;
            activity.getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                callback
            );
            return callback;
        }

        static void unregister(ArchRogueActivity activity, Object callback) {
            activity.getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(
                (OnBackInvokedCallback) callback
            );
        }
    }
}
