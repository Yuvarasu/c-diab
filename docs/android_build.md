# Android builds (custom Expo development build, no Expo Go)

C-Diab uses native modules (camera, secure store) and a custom **development client**. It is never run in Expo Go.
`eas.json` has three profiles:

| Profile | Output | Use |
|---|---|---|
| `development` | APK with `expo-dev-client` | day-to-day work on a real phone, hot reload |
| `preview` | installable APK (internal distribution) | testers / demo without a dev server |
| `production` | Android App Bundle (`.aab`) | Google Play |

`app.config.ts` locks release builds down (no dev-overlay permission, no backups of app data, no storage/contacts/location/SMS/microphone permissions). The merged manifest of a production build requests only **CAMERA, INTERNET, VIBRATE**; development additionally has the dev-menu overlay permission.

## One-time setup
```bash
cd mobile
npm install
npx expo install --check && npx expo-doctor
npx eas-cli login                      # you sign in; never paste credentials into chat
npx eas-cli init                       # creates the EAS project and writes its id into app.json
```
**Environment variables.** The app needs `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY` at build time. Create them as EAS environment variables for `development`, `preview` and `production` (`npx eas-cli env:create --help`; EAS applies the environment that matches the build profile; confirm with `eas env:list`). They are public by nature. `EXPO_PUBLIC_APP_ENV` is set per profile in `eas.json`.
The `production` API URL must be **HTTPS** and must not point at a development machine.

## Development build → phone
```bash
npx eas-cli build --platform android --profile development     # downloads an APK link when done
```
Install the APK on the phone (open the build link / scan the QR; allow installs from your browser if asked). Then:
```bash
npx expo start --dev-client            # phone and computer on the same Wi-Fi; open the C-Diab dev app, pick the server
```
Saving a file hot-reloads the installed app. Rebuild only when native dependencies or `app.json`/`app.config.ts` plugins change.
For a local API use your computer's LAN address, e.g. `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000` (development builds only).

## Preview APK
```bash
npx eas-cli build --platform android --profile preview
```
Install the APK. It uses the preview environment variables and the backend you point it at. With `AI_BACKEND=demo` all results are labelled DEMO.

## Production AAB and signing
```bash
npx eas-cli build --platform android --profile production      # versionCode auto-increments (managed by EAS)
```
On the first build EAS offers to generate and store an upload keystore: accept (`eas credentials` shows/downloads it; back it up). Use **Play App Signing** in the Play Console. The build prints a download link for the `.aab`.

### Upload to Google Play
1. Play Console → create the app → **Testing → Internal testing → Create new release** → upload the `.aab` → roll out to your tester list.
2. Complete **Policy → App content** (privacy policy, Data safety, Health apps declaration, ads, target audience…). See `play_store_release.md`.
3. Promote to closed/open/production when everything is green. Alternatively `npx eas-cli submit --platform android --profile production` (needs a Google service-account key you create in the Play Console).

### Check the target API level of what you built
Google requires new apps and updates to target Android 16 (**API 36**) since 31 Aug 2026. React Native 0.86's defaults are `targetSdk 36`, `compileSdk 36`, `minSdk 24` (see `node_modules/react-native/gradle/libs.versions.toml`). Confirm on the artifact:
```bash
aapt2 dump badging app.apk | grep -E "targetSdkVersion|package:"        # APK
bundletool dump manifest --bundle app.aab | grep -i targetSdk            # AAB
```

## Honest status
No APK/AAB has been built by this repository's author: building needs your Expo login and (for Play) a Play developer account. What *was* verified here: `expo-doctor` config checks, TypeScript (0 errors), 27 unit/screen tests, a full **Metro/Hermes Android bundle export**, and `expo prebuild` producing `com.cdiab.app`, version 1.0.0 / code 1 and the permission list above.
