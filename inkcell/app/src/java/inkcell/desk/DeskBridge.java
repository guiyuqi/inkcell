package inkcell.desk;

import android.util.Base64;
import android.webkit.JavascriptInterface;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * 给页面用的 JS 桥（顶层类：本机的 d8 不能吃非静态内部类）。
 * 方法都在 WebView 的 JS 线程上执行，可以直接做文件 IO。
 */
public class DeskBridge {

    private final MainActivity act;
    private final File root;
    private final File glyphDir;

    public DeskBridge(MainActivity act, File root, File glyphDir) {
        this.act = act;
        this.root = root;
        this.glyphDir = glyphDir;
    }

    /** 一份 {id, char, pass, png, strokes, px_per_mm, pressure} 落成 png + json。 */
    @JavascriptInterface
    public void saveGlyph(String jsonStr) {
        try {
            JSONObject o = new JSONObject(jsonStr);
            int id = o.getInt("id");
            String ch = o.optString("char", " ");
            int pass = o.optInt("pass", 1);
            String code = (ch.isEmpty() || " ".equals(ch))
                    ? "sp" : String.format(Locale.US, "%05x", ch.codePointAt(0));
            String base = String.format(Locale.US, "%04d_p%d_%s", id, pass, code);
            String png = o.optString("png", "");
            o.remove("png");
            write(new File(glyphDir, base + ".json"), o.toString().getBytes(StandardCharsets.UTF_8));
            if (!png.isEmpty()) {
                write(new File(glyphDir, base + ".png"), Base64.decode(png, Base64.DEFAULT));
            }
        } catch (Exception e) {
            say("落盘失败：" + e);
        }
    }

    @JavascriptInterface
    public int countGlyphs() {
        String[] fs = glyphDir.list();
        if (fs == null) return 0;
        int n = 0;
        for (String f : fs) if (f.endsWith(".png")) n++;
        return n;
    }

    /** 已经落盘的格子 id 列表（页面用它在启动时恢复进度）。 */
    @JavascriptInterface
    public String savedIds() {
        StringBuilder sb = new StringBuilder("[");
        String[] fs = glyphDir.list();
        if (fs != null) {
            java.util.TreeSet<Integer> ids = new java.util.TreeSet<Integer>();
            for (String f : fs) {
                if (!f.endsWith(".png")) continue;
                int us = f.indexOf('_');
                if (us <= 0) continue;
                try {
                    ids.add(Integer.parseInt(f.substring(0, us)));
                } catch (NumberFormatException ignored) {
                    // 名字不是 id 开头的文件，跳过
                }
            }
            for (Integer id : ids) {
                if (sb.length() > 1) sb.append(',');
                sb.append(id.intValue());
            }
        }
        return sb.append(']').toString();
    }

    /** 读回一格已经写过的字（PNG base64），页面用它画"灰字底稿"。 */
    @JavascriptInterface
    public String readGlyph(int id) {
        String prefix = String.format(Locale.US, "%04d_p", id);
        String[] fs = glyphDir.list();
        if (fs != null) {
            for (String f : fs) {
                if (f.startsWith(prefix) && f.endsWith(".png")) {
                    try {
                        return Base64.encodeToString(
                                readAll(new File(glyphDir, f)), Base64.NO_WRAP);
                    } catch (Exception e) {
                        return "";
                    }
                }
            }
        }
        return "";
    }

    /** 删掉某一格（重写本屏用）。 */
    @JavascriptInterface
    public void deleteGlyph(int id) {
        String prefix = String.format(Locale.US, "%04d_p", id);
        String[] fs = glyphDir.list();
        if (fs == null) return;
        for (String f : fs) {
            if (f.startsWith(prefix)) {
                //noinspection ResultOfMethodCallIgnored
                new File(glyphDir, f).delete();
            }
        }
    }

    /** 「重置本地」用：删掉 App 目录里所有已落的格子。 */
    @JavascriptInterface
    public void clearGlyphs() {
        String[] fs = glyphDir.list();
        if (fs == null) return;
        int n = 0;
        for (String f : fs) {
            if (f.endsWith(".png") || f.endsWith(".json")) {
                if (new File(glyphDir, f).delete()) n++;
            }
        }
        say("已删除 " + n + " 个文件");
    }

    /** 页面里自己打好的整包 ZIP 写到 App 目录。 */
    @JavascriptInterface
    public void saveZip(String b64) {
        try {
            String ts = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date());
            File f = new File(root, "desk-export-" + ts + ".zip");
            write(f, Base64.decode(b64, Base64.DEFAULT));
            say("已导出 " + f.getName());
        } catch (Exception e) {
            say("导出失败：" + e);
        }
    }

    @JavascriptInterface
    public String where() {
        return root == null ? "" : root.getAbsolutePath();
    }

    @JavascriptInterface
    public void toast(String msg) {
        say(msg);
    }

    private byte[] readAll(File f) throws IOException {
        FileInputStream in = new FileInputStream(f);
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        } finally {
            in.close();
        }
    }

    private void write(File f, byte[] data) throws IOException {
        File parent = f.getParentFile();
        if (parent != null && !parent.exists()) parent.mkdirs();
        FileOutputStream out = new FileOutputStream(f);
        try {
            out.write(data);
        } finally {
            out.close();
        }
    }

    private void say(String msg) {
        act.runOnUiThread(new Toaster(act, msg));
    }
}
