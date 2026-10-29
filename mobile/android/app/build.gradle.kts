import com.android.build.api.variant.ApplicationVariant
import com.android.build.api.variant.impl.VariantOutputImpl
import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("com.google.gms.google-services")
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.cashctrl"
    compileSdk = 37
    ndkVersion = "28.2.13676358"

    compileOptions {
        // Flag to enable support for the new language APIs
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget = JvmTarget.JVM_17
        }
    }

    sourceSets {
        getByName("main").java.directories.add("src/main/kotlin")
    }

    val localProperties = Properties()
    val localPropertiesFile = rootProject.file("local.properties")
    if (localPropertiesFile.exists()) {
        localPropertiesFile.reader(Charsets.UTF_8).use { reader ->
            localProperties.load(reader)
        }
    }

    var flutterVersionCode = localProperties.getProperty("flutter.versionCode")
    if (flutterVersionCode == null) {
        flutterVersionCode = "1"
    }

    var flutterVersionName = localProperties.getProperty("flutter.versionName")
    if (flutterVersionName == null) {
        flutterVersionName = "1.0"
    }

    defaultConfig {
        applicationId = "com.cashctrl"
        // You can update the following values to match your application needs.
        // For more information, see: https://docs.flutter.dev/deployment/android#reviewing-the-build-configuration.
        minSdk = 26
        targetSdk = 37
        versionCode = flutterVersionCode.toInt()
        versionName = flutterVersionName
    }

    buildFeatures {
        resValues = true
    }

    signingConfigs {
        getByName("debug") {
            // Override the local debug keystore, so that all builds have consistent certificates.
            storeFile = file("debug.keystore")
        }
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    // Define a variable that contains the app's name and use it for naming the .apk file
    // Check if an applicationName property is supplied; if not use the name of the parent project.
    val appName = if (project.hasProperty("applicationName")) {
        project.findProperty("applicationName") as String
    } else {
        parent?.name
    }

    androidComponents {
        onVariants { variant ->
            renameAPK(variant, appName)
        }
    }

    // Print a helpful message that tells the developer where the renamed apk is placed.
    var variantName = gradle.startParameter.taskNames[0].replace("assemble", "")
    variantName = variantName[0].lowercaseChar() + variantName.substring(1)
    val variantPath = variantName.split("(?=\\p{Upper})").joinToString("/").lowercase()
    val text = "The renamed apk file can be found at: build/app/outputs/apk/" +
            "${variantPath}/$appName-$variantName-${defaultConfig.versionName}.apk"
    println()
    println(" ${"-".repeat(text.length + 2)} ")
    println("| $text |")
    println(" ${"-".repeat(text.length + 2)} ")
    println()
}

/**
 * Sets a user friendly output file name to the given [variant] by including the app name, the
 * variant's name (aka app type: *debug, debugDev, live, liveDev, etc*) and the app's version.
 *
 * @param variant the current variant
 * @param appName the app's name
 */
fun renameAPK(variant: ApplicationVariant?, appName: String?) {
    variant?.outputs?.forEach {
        it as VariantOutputImpl
        it.outputFileName.set("${appName}-${variant.name}-${it.versionName.get()}.apk")
    }
}

flutter {
    source = "../.."
}

dependencies {
    implementation("androidx.window:window:1.5.1")
    implementation("androidx.window:window-java:1.5.1")
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}
