# Automated APK Build & Distribution

Push code → GitHub Actions builds a **signed** release APK → publishes it to a
**GitHub Release** and **Firebase App Distribution** → testers get an email with
a download link. No more manual builds or WhatsApp sharing.

The workflow lives at `.github/workflows/android-distribute.yml` and runs on
every push to `master` that touches `apps/mobile/**` (or manually from the
Actions tab via "Run workflow").

---

## One-time setup

### 1. Signing keystore (already generated)

A release keystore was generated at `apps/mobile/android/upload-keystore.jks`
(git-ignored, never committed). Its base64 form is on your Desktop as
`ANDROID_KEYSTORE_BASE64.txt`.

> ⚠️ **Back up `upload-keystore.jks` and its password somewhere safe** (password
> manager / private drive). If you ever publish to the Play Store this key is
> your app's permanent identity — losing it means you can't ship updates.

| Field          | Value             |
| -------------- | ----------------- |
| Store password | `RoadSide2026!ks` |
| Key password   | `RoadSide2026!ks` |
| Key alias      | `upload`          |

### 2. GitHub repository secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**.
Add these (the first four are required; Firebase ones can come later):

| Secret name              | Value                                                    |
| ------------------------ | -------------------------------------------------------- |
| `ANDROID_KEYSTORE_BASE64`| Entire contents of `Desktop/ANDROID_KEYSTORE_BASE64.txt` |
| `ANDROID_STORE_PASSWORD` | `RoadSide2026!ks`                                        |
| `ANDROID_KEY_PASSWORD`   | `RoadSide2026!ks`                                        |
| `ANDROID_KEY_ALIAS`      | `upload`                                                 |
| `FIREBASE_ANDROID_APP_ID`| From Firebase (step 3), e.g. `1:1234567890:android:abc…` |
| `FIREBASE_SERVICE_ACCOUNT`| Full JSON of the service account (step 3)               |

With just the first four set, every push produces a **GitHub Release** with the
APK attached. The Firebase step is skipped until its secrets exist.

### 3. Firebase App Distribution

1. Go to <https://console.firebase.google.com> → **Add project** → name it
   *RoadSide Agent* (Analytics optional, can disable).
2. In the project, click the **Android** icon to add an app.
   - **Package name:** `com.roadsideagent.roadside_mobile` (must match exactly).
   - Register the app. You can **skip** downloading `google-services.json` — it's
     only needed if the app itself uses Firebase SDKs; App Distribution doesn't.
3. **Project Settings → General → Your apps** → copy the **App ID**
   (`1:…:android:…`) → save as the `FIREBASE_ANDROID_APP_ID` secret.
4. Left nav → **Release & Monitor → App Distribution → Get started**.
5. **Testers & Groups** tab → create a group named **`testers`** (this exact name
   matches the workflow) → add your friend's email.
6. Create a service account for CI:
   - Google Cloud Console → **IAM & Admin → Service Accounts → Create**.
   - Grant role **Firebase App Distribution Admin**.
   - **Keys → Add key → JSON** → download.
   - Paste the whole JSON file's contents as the `FIREBASE_SERVICE_ACCOUNT` secret.

### 4. Your friend (tester) — one time

They'll get an email from Firebase App Distribution → tap **Get started** →
accept the invite → install the **App Tester** app (or download directly). Every
new build after that pings them automatically with a download link.

---

## Daily workflow after setup

1. Make Flutter changes, commit, `git push`.
2. GitHub Actions builds + signs + distributes automatically (~5–8 min).
3. Friend gets an email and installs the latest APK. Done.

Because every build uses the same keystore, updates install **over the top** —
no uninstall/reinstall needed.
