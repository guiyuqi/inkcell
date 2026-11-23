package inkcell.desk;

import android.app.Activity;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * 写字台（离线 APK）。
 *
 * 页面是完整的自包含 HTML（由 TOOLS/writing_desk.py --offline-out 生成），
 * 手写数据先落 WebView 的 IndexedDB，再经 DeskBridge 另存一份到
 * /sdcard/Android/data/inkcell.desk/files/glyphs/，拔线也能用 MTP 拷出来。
 *
 * 注意：本文件刻意不出现「非静态内部类 / 匿名类」——本机 build-tools 34 的 d8
 * 遇到带 this$0 的类会崩（NullPointerException: String.length()）。全部用顶层类。
 */
public class MainActivity extends Activity {

    private WebView web;
    private File root;
    private long lastBack = 0L;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        hideSystemBars();

        root = getExternalFilesDir(null);
        if (root == null) root = getFilesDir();
        File glyphDir = new File(root, "glyphs");
        glyphDir.mkdirs();

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(false);
        s.setUseWideViewPort(false);
        s.setBuiltInZoomControls(false);
        s.setSupportZoom(false);
        s.setTextZoom(100);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);

        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient());
        web.addJavascriptInterface(new DeskBridge(this, root, glyphDir), "DeskBridge");
        web.setBackgroundColor(0xFF22252A);
        setContentView(web);

        String html;
        try {
            html = readAsset("desk.html");
        } catch (IOException e) {
            html = "<h1 style='color:#fff;font-family:sans-serif'>页面缺失：" + e + "</h1>";
        }
        // 用正常的 https 来源加载，IndexedDB 才可用
        web.loadDataWithBaseURL("https://desk.local/", html, "text/html", "utf-8", null);
    }

    public File getRoot() {
        return root;
    }

    private void hideSystemBars() {
        View d = getWindow().getDecorView();
        d.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
    }

    private String readAsset(String name) throws IOException {
        InputStream in = getAssets().open(name);
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        } finally {
            in.close();
        }
    }

    @Override
    public boolean onKeyDown(int code, KeyEvent e) {
        if (web != null && (code == KeyEvent.KEYCODE_VOLUME_UP || code == KeyEvent.KEYCODE_VOLUME_DOWN)) {
            // 音量键当快捷键：音量+ 存这一屏，音量- 撤回
            web.evaluateJavascript(
                    code == KeyEvent.KEYCODE_VOLUME_UP ? "save(false)" : "undo()", null);
            return true;
        }
        return super.onKeyDown(code, e);
    }

    @Override
    public void onBackPressed() {
        // 不用返回键退出，免得写字时误触；两秒内连按两次才退
        long now = System.currentTimeMillis();
        if (now - lastBack < 1800) {
            super.onBackPressed();
        } else {
            lastBack = now;
            Toast.makeText(this, "再按一次返回键退出", Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (web != null) web.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        hideSystemBars();
        if (web != null) web.onResume();
    }
}
