#!/bin/bash
# PhoneBox APK 构建（服务器侧全自动）：JDK17 + 腾讯 AndroidSDK 镜像 + 腾讯 Gradle + 阿里 Maven 镜像
B=/mnt/nvme0n1p1/temp/phonebox-deploy-20261111-164402
L=$B/build.log
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
SDK=$HOME/android-sdk
T=https://mirrors.cloud.tencent.com/AndroidSDK
say(){ echo "$(date +%T) $*"; }
{
  say STEP_WAIT_JDK
  i=0; while [ ! -x "$JAVA_HOME/bin/java" ] && [ $i -lt 120 ]; do sleep 5; i=$((i+1)); done
  java -version 2>&1 | head -1 || { say JDK_MISSING; exit 1; }

  say STEP_SDK
  mkdir -p $SDK/platforms $SDK/build-tools /tmp/sdkdl
  [ -f $SDK/platforms/android-35/android.jar ] || {
    curl -sSf --connect-timeout 15 -o /tmp/sdkdl/p35.zip $T/platform-35_r01.zip &&
    unzip -q -o /tmp/sdkdl/p35.zip -d $SDK/platforms/android-35/
  }
  [ -f $SDK/build-tools/34.0.0/aapt2 ] || {
    curl -sSf --connect-timeout 15 -o /tmp/sdkdl/bt.zip $T/build-tools_r34-linux.zip &&
    unzip -q -o /tmp/sdkdl/bt.zip -d $SDK/build-tools/34.0.0/
  }
  [ -f $SDK/platforms/android-35/android.jar ] || { say SDK_PLATFORM_FAIL; exit 1; }
  [ -f $SDK/build-tools/34.0.0/aapt2 ] || { say SDK_BUILDTOOLS_FAIL; exit 1; }
  echo "sdk.dir=$SDK" > $HOME/phonebox/android/local.properties

  say STEP_MIRRORS
  sed -i "s#https\\\\://services.gradle.org/distributions#https\\\\://mirrors.cloud.tencent.com/gradle#" $HOME/phonebox/android/gradle/wrapper/gradle-wrapper.properties
  grep distributionUrl $HOME/phonebox/android/gradle/wrapper/gradle-wrapper.properties
  mkdir -p $HOME/.gradle
  cat > $HOME/.gradle/init.gradle <<'INIT'
beforeSettings { s ->
  s.pluginManagement.repositories {
    maven { url 'https://maven.aliyun.com/repository/gradle-plugin' }
    maven { url 'https://maven.aliyun.com/repository/google' }
    maven { url 'https://maven.aliyun.com/repository/public' }
    gradlePluginPortal(); google(); mavenCentral()
  }
  s.dependencyResolutionManagement.repositories {
    maven { url 'https://maven.aliyun.com/repository/google' }
    maven { url 'https://maven.aliyun.com/repository/public' }
  }
}
INIT

  say STEP_GRADLE_BOOT
  cd $HOME/phonebox/android || { say NO_ANDROID_DIR; exit 1; }
  chmod +x gradlew
  if ! timeout 900 ./gradlew -v >/dev/null 2>&1; then
    say GRADLE_TENCENT_TRY_FAILED_fallback_services
    sed -i "s#https\\\\://mirrors.cloud.tencent.com/gradle#https\\\\://services.gradle.org/distributions#" gradle/wrapper/gradle-wrapper.properties
  fi
  timeout 1800 ./gradlew -v >/dev/null || { say GRADLE_BOOT_FAIL; exit 1; }

  say STEP_BUILD
  timeout 3000 ./gradlew assembleRelease --console=plain --stacktrace 2>&1 | tail -30
  echo "--- outputs ---"
  ls -la app/build/outputs/apk/release/ 2>/dev/null || { say NO_APK_OUTPUT; exit 1; }
  say BUILD_ALL_DONE
} >> $L 2>&1
