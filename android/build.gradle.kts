buildscript {
    val toolchain = java.util.Properties().apply {
        rootProject.file("toolchain.properties").inputStream().use { load(it) }
    }
    val agpVersion = toolchain.getProperty("AGP_VERSION")
        ?: throw GradleException("AGP_VERSION is missing from android/toolchain.properties")
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        // Pin the implementation coordinate directly so offline builds do not
        // depend on a separately cached Gradle plugin-marker artifact.
        classpath("com.android.tools.build:gradle:$agpVersion")
    }
}
