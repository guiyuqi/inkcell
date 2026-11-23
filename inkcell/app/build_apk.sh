#!/usr/bin/env bash
# inkcell/app/build_apk.sh —— 把「写字台」打成离线 APK。
# 不需要 Android Studio / Gradle：aapt2 + javac + d8 + zipalign + apksigner。
#
# 依赖：本机 Android SDK（找 $ANDROID_HOME / $ANDROID_SDK_ROOT / /opt/android-sdk / 本目录 _sdk）
# 用法：
#   inkcell app                          # 默认：项目=当前目录，tag=corpus，第 1 遍
#   PROJECT=../myproj TAG=gb2312 ALL=1 inkcell app
#   TAG=gb2312 PASS=0 inkcell app --project ../myproj
set -euo pipefail

APP=$(cd "$(dirname "$0")" && pwd)          # inkcell/app
PKG=$(cd "$APP/.." && pwd)                  # inkcell（包目录）
PY=${PY:-python3}
PROJECT=${PROJECT:-$(pwd)}
TAG=${TAG:-corpus}
PASS=${PASS:-1}
OUT=${OUT:-$APP/写字台.apk}
BUILD=$APP/build

# --- 找 SDK ---
SDK=$(for d in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" /opt/android-sdk "$APP/_sdk"; do
        [ -n "$d" ] && [ -d "$d/build-tools" ] && { echo "$d"; break; }
      done)
[ -n "$SDK" ] || { echo "!! 找不到 Android SDK（先跑 inkcell/app/ensure_sdk.sh 或设 ANDROID_HOME）"; exit 2; }
BT=$(ls -d "$SDK"/build-tools/*/ 2>/dev/null | sort -V | tail -1 | sed 's:/$::')
PLAT=$(ls -d "$SDK"/platforms/android-*/ 2>/dev/null | sort -V | tail -1 | sed 's:/$::')
AJAR="$PLAT/android.jar"
echo "   SDK: $SDK"
echo "   build-tools: $BT"

echo "== 1/6 生成离线页面（$TAG / $([ "${ALL:-0}" = 1 ] && echo 整本 || echo 第\ $PASS\ 遍)）"
if [ "${ALL:-0}" = "1" ]; then
  PYTHONPATH="$PKG" "$PY" -m inkcell.cli desk --project "$PROJECT" --tag "$TAG" --all-passes \
        --offline-out "$APP/src/assets/desk.html"
else
  PYTHONPATH="$PKG" "$PY" -m inkcell.cli desk --project "$PROJECT" --tag "$TAG" --pass-id "$PASS" \
        --offline-out "$APP/src/assets/desk.html"
fi

echo "== 2/6 生成图标"
PYTHONPATH="$PKG" "$PY" -c "import sys; from inkcell.app import make_icons; sys.exit(make_icons.main())" \
  || PYTHONPATH="$PKG" "$PY" "$APP/make_icons.py"

rm -rf "$BUILD"; mkdir -p "$BUILD/res" "$BUILD/gen" "$BUILD/classes" "$BUILD/dex"

echo "== 3/6 资源编译 / 链接"
"$BT/aapt2" compile --dir "$APP/src/res" -o "$BUILD/res.zip"
"$BT/aapt2" link -o "$BUILD/base.apk" -I "$AJAR" \
    --manifest "$APP/src/AndroidManifest.xml" -A "$APP/src/assets" \
    --min-sdk-version 24 --target-sdk-version 33 \
    --java "$BUILD/gen" --auto-add-overlay "$BUILD/res.zip"

echo "== 4/6 编译 Java"
find "$BUILD/gen" -name '*.java' > "$BUILD/sources.txt"
find "$APP/src/java" -name '*.java' >> "$BUILD/sources.txt"
javac -nowarn -Xlint:-options --release 8 -classpath "$AJAR" -d "$BUILD/classes" @"$BUILD/sources.txt" 2>&1 \
  | grep -v '^Note:' || true

echo "== 5/6 转 dex"
"$BT/d8" --lib "$AJAR" --min-api 24 --output "$BUILD/dex" $(find "$BUILD/classes" -name '*.class')

echo "== 6/6 打包 / 对齐 / 签名"
cp "$BUILD/base.apk" "$BUILD/unsigned.apk"
( cd "$BUILD/dex" && zip -q -X "$BUILD/unsigned.apk" classes.dex )
"$BT/zipalign" -f -p 4 "$BUILD/unsigned.apk" "$BUILD/aligned.apk"
KS=${KS:-$APP/debug.keystore}
if [ ! -f "$KS" ]; then
  keytool -genkeypair -keystore "$KS" -storepass android -keypass android \
      -alias desk -keyalg RSA -keysize 2048 -validity 10950 \
      -dname "CN=inkcell, O=inkcell, C=CN" >/dev/null 2>&1
  echo "   已生成自签名 keystore（仅自己装用；别提交）"
fi
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android \
    --min-sdk-version 24 --out "$OUT" "$BUILD/aligned.apk"
"$BT/apksigner" verify --min-sdk-version 24 "$OUT" >/dev/null && echo "   签名验证通过"
ls -lh "$OUT" | awk '{print "== 完成：" $9 "  " $5}'
