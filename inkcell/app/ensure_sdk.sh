#!/usr/bin/env bash
# inkcell/app/ensure_sdk.sh —— 本机没有 Android SDK 时，下载最小的一套到 app/_sdk/
#
# 只为了打一个 WebView APK，不需要 Android Studio。
#   inkcell/app/ensure_sdk.sh
set -euo pipefail
cd "$(dirname "$0")"
SDK=$PWD/_sdk
if [ -d "$SDK/build-tools" ] && [ -d "$SDK/platforms" ]; then echo "已有 $SDK"; exit 0; fi
PROXY=${PROXY:-}
if [ -n "$PROXY" ]; then export http_proxy=$PROXY https_proxy=$PROXY; fi
mkdir -p "$SDK" && cd "$SDK"
echo "== 下载 build-tools 34（腾讯镜像）"
curl -L --retry 3 -o build-tools.zip "https://mirrors.cloud.tencent.com/AndroidSDK/build-tools_r34-linux.zip"
echo "== 下载 platform 35（dl.google.com）"
curl -L --retry 3 -o platform.zip "https://dl.google.com/android/repository/platform-35_r02.zip"
unzip -q -o build-tools.zip && unzip -q -o platform.zip
rm -f build-tools.zip platform.zip
mkdir -p build-tools platforms
[ -d android-14 ] && mv android-14 build-tools/34.0.0      # r34 包内目录名就是 android-14
[ -d android-35 ] && mv android-35 platforms/android-35
chmod +x build-tools/*/aapt2 build-tools/*/d8 build-tools/*/apksigner build-tools/*/zipalign
echo "== 好了：$SDK"
