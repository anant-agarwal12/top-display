# Code signing

Top Display's installer is currently **unsigned**, so Windows SmartScreen shows "Windows protected
your PC" with an unknown publisher the first time someone runs it. Signing the installer (and the
app) with a certificate from a certificate authority Windows trusts replaces "Unknown publisher"
with a verified name.

The build is already prepared for it. Signing switches on by itself the moment a certificate is
configured; with none configured the build is simply unsigned.

## What signing does and does not do
- It proves who published the file and that it has not been modified since.
- It does **not** instantly remove the SmartScreen warning. SmartScreen also judges how many people
  have run a file, so a new publisher can still see a warning for a while. Ordinary (OV) and
  extended (EV) certificates both build that reputation over time.
- A **self-signed** certificate protects nothing for other people: Windows does not trust it, and
  to make it work every user would have to install your certificate as trusted, which they should
  not do. It is only useful for testing the build (the repository's tests use a throwaway one).

## Ways to get a certificate
You need a real identity check by someone, so this part cannot be automated. In rough order of fit
for a small open-source project:

1. **SignPath Foundation** (free for open-source projects). The project must be public, use an
   OSI-approved license (GPL-3.0 qualifies) and build in CI; they sign in their cloud, so the key
   never leaves their hardware. The published name is the foundation's. Apply at signpath.org and
   check their current conditions. Signing then happens from the GitHub Actions workflow via their
   action instead of `sign.ps1`.
2. **Azure Artifact Signing** (formerly Trusted Signing), a low monthly fee. Eligibility depends on
   country and on whether you are an individual or an organisation, so check that it is available
   to you before relying on it.
3. **A commercial code-signing certificate** (DigiCert, Sectigo, SSL.com and others, roughly
   US$100-400 a year). Since 2023 the private key must live on hardware (a USB token) or in the
   authority's cloud HSM, so you cannot simply export a `.pfx`. Use the thumbprint option below
   for a token that appears in the Windows certificate store, or the authority's own signing tool
   for a cloud HSM.

## Turning signing on
Set these environment variables, then run `packaging\build.ps1` as usual
(`packaging\sign.ps1` documents them too):

| Variable | Meaning |
| --- | --- |
| `TD_SIGN_PFX` | path to a `.pfx` file (only if your authority gives you an exportable one) |
| `TD_SIGN_PFX_PASSWORD` | its password |
| `TD_SIGN_THUMBPRINT` | alternatively, the thumbprint of a certificate in your Windows certificate store (hardware tokens usually appear there) |
| `TD_SIGN_TIMESTAMP_URL` | optional; defaults to `http://timestamp.digicert.com` |

The build then signs `TopDisplay.exe`, the installer, and the uninstaller the installer writes,
all with a timestamp (without one, a signature stops being valid the day the certificate expires,
so signing fails rather than skipping it). It ends by printing who signed the installer.

Check any file yourself with:

```powershell
Get-AuthenticodeSignature dist\TopDisplay-Setup-<version>.exe | Format-List Status, SignerCertificate, TimeStamperCertificate
```
`Valid` means signed by a trusted authority. `UnknownError` with a signer present means signed but
by a certificate Windows does not trust (for example the test certificate).

## Signing in GitHub Actions
The release workflow (manual runs only) will sign if two repository secrets exist:
`SIGNING_PFX_BASE64` (the `.pfx`, base64-encoded) and `SIGNING_PFX_PASSWORD`. This only suits an
exportable certificate, and it has not been run against a real one yet because none exists. For
SignPath or a cloud HSM the workflow step is different; ask when you get that far.

Never commit a `.pfx`, a password, or a token. `.gitignore` already excludes `*.pfx`.
