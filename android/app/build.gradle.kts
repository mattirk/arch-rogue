import java.io.File
import java.nio.file.Files
import java.util.Properties

plugins {
    id("com.android.application")
}

fun Properties.required(name: String): String =
    getProperty(name)?.takeIf { it.isNotBlank() }
        ?: throw GradleException("Missing $name in android/toolchain.properties")

if (JavaVersion.current() != JavaVersion.VERSION_17) {
    throw GradleException("Arch Rogue Android requires JDK 17; Gradle is using ${JavaVersion.current()}")
}

val toolchain = Properties().apply {
    rootProject.file("toolchain.properties").inputStream().use { load(it) }
}
val releaseApplicationId = toolchain.required("RELEASE_APPLICATION_ID")
val debugApplicationId = toolchain.required("DEBUG_APPLICATION_ID")
if (!releaseApplicationId.endsWith(".odin.alpha")) {
    throw GradleException("Release application id must remain on the .odin.alpha track")
}
if (debugApplicationId != "$releaseApplicationId.debug") {
    throw GradleException("Debug application id must be $releaseApplicationId.debug")
}
val expectedAbis = toolchain.required("ANDROID_ABIS")
    .split(',')
    .map { it.trim() }
    .filter { it.isNotEmpty() }
    .toSet()
if (expectedAbis != setOf("arm64-v8a", "armeabi-v7a", "x86_64")) {
    throw GradleException("ANDROID_ABIS must be exactly arm64-v8a,armeabi-v7a,x86_64")
}

val generatedRoot = rootProject.layout.projectDirectory.dir("../build/android/generated")
val versionFile = generatedRoot.file("version.properties").asFile
if (!versionFile.isFile) {
    throw GradleException(
        "Missing generated version metadata: ${versionFile.path}. " +
            "Use ./build.sh android-debug or ./build.sh android-release from the repository root."
    )
}
val generatedVersion = Properties().apply {
    versionFile.inputStream().use { load(it) }
}
val versionNameValue = generatedVersion.required("versionName")
val versionCodeValue = generatedVersion.required("versionCode").toIntOrNull()
    ?: throw GradleException("versionCode is invalid in ${versionFile.path}")

val signingEnvironment = mapOf(
    "ARCH_ROGUE_ANDROID_KEYSTORE" to System.getenv("ARCH_ROGUE_ANDROID_KEYSTORE"),
    "ARCH_ROGUE_ANDROID_STORE_PASSWORD" to System.getenv("ARCH_ROGUE_ANDROID_STORE_PASSWORD"),
    "ARCH_ROGUE_ANDROID_KEY_ALIAS" to System.getenv("ARCH_ROGUE_ANDROID_KEY_ALIAS"),
    "ARCH_ROGUE_ANDROID_KEY_PASSWORD" to System.getenv("ARCH_ROGUE_ANDROID_KEY_PASSWORD"),
)
val releaseSigningComplete = signingEnvironment.values.all { !it.isNullOrBlank() }
val releaseSigningPartial = signingEnvironment.values.any { !it.isNullOrBlank() } && !releaseSigningComplete
if (releaseSigningPartial) {
    throw GradleException("Release signing environment is incomplete; set all four ARCH_ROGUE_ANDROID_* values")
}
val releaseRequested = gradle.startParameter.taskNames.any {
    it.contains("Release", ignoreCase = true)
}
if (releaseRequested && !releaseSigningComplete) {
    throw GradleException(
        "Release signing is gated. Set ARCH_ROGUE_ANDROID_KEYSTORE, " +
            "ARCH_ROGUE_ANDROID_STORE_PASSWORD, ARCH_ROGUE_ANDROID_KEY_ALIAS, " +
            "and ARCH_ROGUE_ANDROID_KEY_PASSWORD."
    )
}

android {
    namespace = releaseApplicationId
    compileSdk = toolchain.required("COMPILE_SDK").toInt()
    buildToolsVersion = toolchain.required("BUILD_TOOLS_VERSION")
    ndkVersion = toolchain.required("NDK_VERSION")

    defaultConfig {
        applicationId = releaseApplicationId
        minSdk = toolchain.required("MIN_SDK").toInt()
        targetSdk = toolchain.required("TARGET_SDK").toInt()
        versionCode = versionCodeValue
        versionName = versionNameValue
        ndk {
            abiFilters += expectedAbis
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    signingConfigs {
        if (releaseSigningComplete) {
            create("release") {
                storeFile = File(signingEnvironment.getValue("ARCH_ROGUE_ANDROID_KEYSTORE")!!).absoluteFile
                storePassword = signingEnvironment.getValue("ARCH_ROGUE_ANDROID_STORE_PASSWORD")
                keyAlias = signingEnvironment.getValue("ARCH_ROGUE_ANDROID_KEY_ALIAS")
                keyPassword = signingEnvironment.getValue("ARCH_ROGUE_ANDROID_KEY_PASSWORD")
                enableV1Signing = false
                enableV2Signing = true
                enableV3Signing = true
                enableV4Signing = false
            }
        }
    }

    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".debug"
            isDebuggable = true
            isJniDebuggable = true
        }
        getByName("release") {
            isDebuggable = false
            isJniDebuggable = false
            isMinifyEnabled = false
            isShrinkResources = false
            if (releaseSigningComplete) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    sourceSets.getByName("main") {
        jniLibs.srcDir(generatedRoot.dir("jniLibs").asFile)
        assets.srcDir(generatedRoot.dir("assets").asFile)
    }

    buildFeatures {
        buildConfig = false
    }

    packaging {
        jniLibs {
            // minSdk 28 can mmap uncompressed, page-aligned shared libraries.
            useLegacyPackaging = false
        }
    }

    lint {
        abortOnError = true
        checkReleaseBuilds = true
    }
}

val verifyStagedInputs = tasks.register("verifyStagedInputs") {
    group = "verification"
    description = "Reject missing or stale Android native/assets staging before packaging"
    doLast {
        val jniRoot = generatedRoot.dir("jniLibs").asFile
        val expectedNative = expectedAbis.map { "$it/libmain.so" }.toSet()
        val actualNative = if (jniRoot.isDirectory) {
            jniRoot.walkTopDown()
                .filter { it.isFile }
                .map { it.relativeTo(jniRoot).invariantSeparatorsPath }
                .toSet()
        } else {
            emptySet()
        }
        if (actualNative != expectedNative) {
            throw GradleException(
                "Staged native set mismatch: expected ${expectedNative.sorted()}, got ${actualNative.sorted()}"
            )
        }

        val stagedAssets = generatedRoot.dir("assets/assets").asFile
        if (!stagedAssets.isDirectory || stagedAssets.walkTopDown().none { it.isFile }) {
            throw GradleException("Canonical assets were not staged beneath generated/assets/assets")
        }
        listOf(
            "licenses/ARCH_ROGUE_LICENSE.txt",
            "licenses/ARCH_ROGUE_NOTICE.txt",
            "licenses/RAYLIB_LICENSE.txt",
        ).forEach { relative ->
            val file = generatedRoot.file("assets/$relative").asFile
            if (!file.isFile) {
                throw GradleException("Missing staged license: ${file.path}")
            }
        }
        val generatedSymlink = generatedRoot.asFile.walkTopDown()
            .firstOrNull { Files.isSymbolicLink(it.toPath()) }
        if (generatedSymlink != null) {
            throw GradleException("Android staging contains a symbolic link: ${generatedSymlink.path}")
        }
    }
}

tasks.matching { it.name == "preDebugBuild" || it.name == "preReleaseBuild" }.configureEach {
    dependsOn(verifyStagedInputs)
}
