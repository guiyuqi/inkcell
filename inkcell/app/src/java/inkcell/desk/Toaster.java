package inkcell.desk;

import android.content.Context;
import android.widget.Toast;

/** 顶层 Runnable：JS 桥线程没有 Looper，弹 Toast 要回主线程（本机 d8 不能用匿名类）。 */
public class Toaster implements Runnable {

    private final Context ctx;
    private final String msg;

    public Toaster(Context ctx, String msg) {
        this.ctx = ctx;
        this.msg = msg;
    }

    @Override
    public void run() {
        Toast.makeText(ctx, msg, Toast.LENGTH_SHORT).show();
    }
}
