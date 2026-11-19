[app]

title = USC-V1
package.name = uscv1
package.domain = com.ambetronics

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.exclude_dirs = bin, recipes, .github, .buildozer

version = 1.0

# bleak is built from ./recipes (copied from bleak's Android backend);
# it needs pyjnius and the android module for permissions
requirements = python3,kivy,pyjnius,android,bleak,typing_extensions,async_timeout

orientation = portrait
fullscreen = 0

# --- Android ---
android.permissions = BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_SCAN, BLUETOOTH_CONNECT, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION

android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.enable_androidx = True

p4a.local_recipes = ./recipes
# Stable python-for-android release instead of the development branch
p4a.branch = v2026.05.09

[buildozer]
log_level = 2
warn_on_root = 1
