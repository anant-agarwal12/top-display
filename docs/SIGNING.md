# Code signing and distribution

Top Display's direct-download installer is currently **unsigned**, so Windows SmartScreen shows
"Windows protected your PC" with an unknown publisher the first time someone runs it. This page
explains the realistic ways to deal with that. (Facts below were checked against Microsoft's and
SignPath's own pages in October 2026; prices and eligibility change, so re-check before acting.)

## What signing does and does not do
- It proves who published the file and that it has not been modified since.
- It does **not** instantly remove the SmartScreen warning. Since 2024 even EV certificates build
  reputation gradually, like ordinary (OV) ones; a new publisher can still see a warning for a
  while. Signing every release with the same identity lets reputation accumulate.
- A **self-signed** certificate protects nothing for other people: Windows does not trust it and
  blocks it for the public. It is only useful for testing the build, which is how the
  repository's tests use one (a throwaway that is deleted afterwards).

## The options

| Route | Cost | Works from India? | Who is named as publisher | SmartScreen |
| --- | --- | --- | --- | --- |
| **Microsoft Store, packaged as MSIX** | free developer account (no registration fee for individuals) | yes, nearly 200 markets | you, as the Store publisher | no warning; Microsoft signs the package for you, no certificate to buy or renew |
| **Microsoft Store, as an EXE/MSI installer** | needs a certificate from a trusted CA | yes | you | the Store does not sign it for you |
| **SignPath Foundation** (open source) | free | yes | **SignPath Foundation**, not you | builds reputation over time |
| **Azure Artifact Signing** | about US$10 a month | **no**: individuals only in the USA and Canada | you | builds reputation over time |
| **OV certificate** (DigiCert, Sectigo, GlobalSign...) | about US$150-300 a year | yes | you | builds reputation over time |
| **EV certificate** | US$400+ a year | yes | you | same as OV since 2024, so not worth it for this |

### SignPath Foundation: the conditions that matter
- An OSI-approved license (GPL-3.0 qualifies) and **no commercial dual-licensing**. If you may
  sell a separate commercial license later, this route is closed.
- The project must be actively maintained, already released in the form to be signed, and public.
- A "Code Signing Policy" must be shown on the project's homepage or download page: who the
  committers, reviewers and approvers are, a privacy statement, and a credit to SignPath.
- Every release is approved by hand before signing; team members use two-factor authentication.
- Acceptance is at their discretion, and they look for an established project.

### OV certificate
Since June 2023 the private key must live on hardware (a USB token) or in the authority's cloud
HSM, so you cannot just export a `.pfx` for CI. Use the thumbprint option below for a token that
shows up in the Windows certificate store, or the authority's own signing tool for a cloud HSM.

## What this repo already does
The build is prepared for signing. It switches on by itself when a certificate is configured;
with none configured the build is simply unsigned. Set these, then run `packaging\build.ps1`:

| Variable | Meaning |
| --- | --- |
| `TD_SIGN_PFX` | path to a `.pfx` file (only if your authority gives you an exportable one) |
| `TD_SIGN_PFX_PASSWORD` | its password |
| `TD_SIGN_THUMBPRINT` | alternatively, the thumbprint of a certificate in your Windows certificate store |
| `TD_SIGN_TIMESTAMP_URL` | optional; defaults to `http://timestamp.digicert.com` |

It then signs `TopDisplay.exe`, the installer and the uninstaller the installer writes, all with
a timestamp (without one a signature stops being valid the day the certificate expires, so
signing fails rather than skipping it). Check any file with:

```powershell
Get-AuthenticodeSignature dist\TopDisplay-Setup-<version>.exe | Format-List Status, SignerCertificate, TimeStamperCertificate
```
`Valid` means signed by a trusted authority. `UnknownError` with a signer present means signed by
a certificate Windows does not trust (for example the test certificate).

The release workflow (manual runs) signs too if the repository secrets `SIGNING_PFX_BASE64` and
`SIGNING_PFX_PASSWORD` exist. That only suits an exportable certificate and has not been run
against a real one. SignPath and cloud-HSM routes need a different workflow step.

Never commit a `.pfx`, a password or a token. `.gitignore` already excludes `*.pfx`.

## Microsoft Store (MSIX): what it would take
Not done yet. Roughly: a Store developer account (government ID and a selfie, free), an MSIX
package built from the PyInstaller output with a manifest (full-trust desktop app, a start-up task
for "start with Windows"), the usual Store assets and listing text, a privacy policy URL
(`docs/PRIVACY.md`), and certification. Differences to plan for: there is no installer wizard in
an MSIX, so shortcuts are chosen in the settings pane; settings written under `%APPDATA%` are
redirected into the package's own folder; and the listing must not use another company's
trademark as a name or keyword (Spotify may be mentioned only to say what the app works with).
