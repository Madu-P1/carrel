# Shipping Carrel — codesigning and notarization

This is the operational runbook for cutting a distributable public-beta DMG.
The build and packaging code (`script/package_public_beta.sh`) is already
correct; the work here is one-time account setup plus two environment
variables.

## Why signing is not optional

`hdiutil` will happily produce a DMG from an unsigned `.app`, and that DMG
runs fine on the machine that built it. On any *other* Mac, Gatekeeper
blocks it: the user sees "Carrel is damaged and can't be opened" or a
right-click-to-open prompt. A signed and notarized DMG opens with no
warning. Notarization is therefore a hard requirement for distribution,
not a speed/quality tradeoff you can skip.

## One-time setup

You need an active Apple Developer account ($99/yr) with a **Developer ID
Application** certificate installed in the login keychain.

1. **Confirm the signing identity is present:**

   ```bash
   security find-identity -v -p codesigning
   ```

   Look for a line containing `Developer ID Application`. The quoted name
   is the value you pass as the identity.

2. **Store notarytool credentials once.** This saves an app-specific
   password (created at appleid.apple.com) into the keychain under a
   profile name you choose:

   ```bash
   xcrun notarytool store-credentials "<profile-name>" \
     --apple-id "<your-apple-id-email>" \
     --team-id "<your-team-id>" \
     --password "<app-specific-password>"
   ```

   You only do this once per machine; `notarytool submit` then reads the
   profile by name.

## The two environment variables

`script/package_public_beta.sh` reads:

| Variable | Meaning |
|----------|---------|
| `CARREL_CODESIGN_IDENTITY` | The Developer ID Application identity string. If unset, the script auto-detects the first `Developer ID Application` identity from the keychain. |
| `CARREL_NOTARY_PROFILE` | The `notarytool` keychain profile name from the `store-credentials` step above. Required for a real (non-`--local-unsigned`) build. |

## Cutting the build

```bash
export CARREL_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export CARREL_NOTARY_PROFILE="<profile-name>"
./script/package_public_beta.sh
```

This builds (Swift in release config via `--release`), codesigns the
`.app` with the hardened runtime, builds the DMG, codesigns the DMG,
submits it to Apple for notarization, waits, staples the ticket, and runs
`validate_public_beta_package.sh` against the result.

## Local testing without signing

For a private build on your own machine only:

```bash
./script/package_public_beta.sh --local-unsigned
```

This produces a DMG but leaves the app unsigned and skips notarization.
The result is **not** distributable — it will be Gatekeeper-blocked on
every other Mac.
