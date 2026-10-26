# Install Delentia on Windows with a double click

The installer is called `Delentia-Setup-<version>.exe` and works like any other program: double-click, press Next until it finishes.

## Download

**[Download Delentia-Setup.exe](https://github.com/delentia-labs/Delentia-OS/releases/latest/download/Delentia-Setup.exe)** (always the newest release) · [all releases and versioned files](https://github.com/delentia-labs/Delentia-OS/releases) · [checksums](https://github.com/delentia-labs/Delentia-OS/releases/latest/download/SHA256SUMS.txt)

* The installer is attached to the first release that carries it (**2.4.0**). Until that release exists the link answers *404*. Releases 2.3.1 and earlier have no installer and no Desk pages: use `pip install delentia-os`.
* **Which version is it?** The installer has the number of the runtime inside it (`Delentia-Setup-2.4.0.exe` installs 2.4.0; `delentia --version` says 2.4.0). "*Public Technical Preview 0.1*" is the name of the milestone this release belongs to, not a version number: see [the versioning policy](../release/VERSIONING_POLICY.md).
* **Check the file before you run it:** in PowerShell, `Get-FileHash .\Delentia-Setup.exe -Algorithm SHA256` must print the value next to `Delentia-Setup.exe` in `SHA256SUMS.txt`.

**Status, plainly:** the installer has been built with the real compiler and installed, started, checked and uninstalled on the author's own machine (results at the end of this page), and CI repeats it on a clean GitHub Windows runner (first run 2026-10-26: installer exit 0, the post-install check 6 of 6, uninstall clean). It has **not** been tried on a computer that is not the author's, it is **not code-signed** (SmartScreen will warn) and it has not been tried offline. This page has two parts: "For users" and "For whoever builds it".

## For users

### Install
1. Double-click `Delentia-Setup-<version>.exe`. No administrator rights; it installs for your account only.
2. Windows may show "Windows protected your PC" (SmartScreen) because the file is not code-signed yet. Press **More info → Run anyway** if you downloaded it from the official release page and its SHA-256 matches the one announced.
3. Press Next. You may choose a desktop icon.
4. The installer copies files, then downloads and installs the parts Delentia needs. **It needs the internet and takes 3-10 minutes.** If it fails, a window says why and where the log (`install.log`) is; connect and run the installer again.
5. When it says it is finished, open the Start menu and start **Delentia**.

### Use
Start menu → **Delentia** has four entries (green icon with eyes):
* **Delentia** starts the program (no black window) and opens it in your browser at `http://localhost:3010`. The first start takes 20-60 seconds.
* **Stop Delentia** stops what Delentia started (and only that).
* **Update Delentia** checks for and installs a newer version (always asks first). See `UPDATES_EN.md`.
* **Check Delentia installation** tests that the program starts and answers on this computer (it uses a throw-away data folder, never yours) and writes `check_install_report.txt`: send that file to whoever is helping you if something is wrong.

First do `FIRST_APPROVER_EN.md` (set up your first approver), then choose a model on the **Models** page.

### Where your data is
* The program is in `%LOCALAPPDATA%\Programs\Delentia`.
* **Your data** (memory, the record of what it did, keys, settings) is in `%USERPROFILE%\.delentia`. Installing, uninstalling and updating **never touch that folder**.
* No service runs at start-up, no start-up entry, no scheduled task. Delentia runs only when you click.

### Uninstall
Settings → Apps → Delentia → Uninstall (or Control Panel). It stops what is running and removes the program folder. Your data stays (delete it yourself if you want it gone; that erases memory and the record for good).

### Troubleshooting
| What you see | What to do |
|---|---|
| The installer says the parts could not be installed | Connect to the internet and run it again. The reason is in `%LOCALAPPDATA%\Programs\Delentia\install.log`. |
| Clicking Delentia shows a "could not start" message window | The message says why. Most often port 8000 or 3010 is used by another program; close it, or read `%USERPROFILE%\.delentia\logs\serve.log`. |
| The browser opens on a blank page or "can't connect" | Wait 30 seconds and refresh (the first start is slow). Still nothing: read `logs\serve.log`. |
| Defender/antivirus warns | The file is not code-signed yet. Check the SHA-256 against the announced one and allow it, or wait for a signed release. |

## For whoever builds the installer (the owner)

### Three downloads (waiting for your permission)
| File | From | Approx. size | Used for |
|---|---|---|---|
| `python-3.12.10-embed-amd64.zip` | https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip | ~10 MB | The portable Python shipped with the program (3.12.10 is the last 3.12 release with binary installers) |
| `get-pip.py` | https://bootstrap.pypa.io/get-pip.py | ~2.5 MB | Installs pip into the portable Python |
| Inno Setup 6 (`innosetup-6.x.exe`) | https://jrsoftware.org/isdl.php | ~5 MB | The program that builds `Setup.exe` (installed on the builder's machine only; it is not inside the user's installer) |

The script **downloads nothing itself**. It takes the files you give it and prints the SHA-256 of each so you can compare with what the publisher announces (also saved in the installer as `SOURCES.json`).

### Build command
```
python installer/windows/build_installer.py --python-embed <python-3.12.10-embed-amd64.zip> --get-pip <get-pip.py>
```
* Without `--wheel` it builds the wheel itself (it runs `scripts/package_desk.py` first so the web pages are inside the package; needs Node.js 20+).
* `--stage-only` lays out the files and stops (no Inno Setup needed); use it to check the layout.
* `--offline-wheels` puts every needed component into the installer: much bigger (hundreds of MB), but it installs with no internet.
* Result: `installer/windows/output/Delentia-Setup-<version>.exe`, with its size and SHA-256 printed.

### Test before handing it out (on a clean Windows machine)
1. A machine without Python (a virtual machine or a new user account).
2. Double-click to install; check that Start → Delentia opens the web page.
3. Complete `FIRST_APPROVER_EN.md`.
4. Uninstall; check that the `.delentia` folder is still there.
5. Code-sign the installer (a code-signing certificate) before giving it to the public, to avoid the SmartScreen warning.

### Checked and not checked
* Checked by automatic tests: the staged layout (portable Python configured so pip and packages are visible, the wheel, the install script), the Inno Setup script (per-user install, no start-up entry, no registry, three shortcuts, never touches `.delentia`, errors shown in a window), the logo files at the sizes the compiler requires, and the `launch` command (start, find again, stop only what it started), run for real with `pythonw` (no black window).
* **Checked for real (2026-10-26, on the builder's machine, Windows 11, normal internet):** the real Inno Setup 6.7.3 compile succeeded in 6 seconds and made `Delentia-Setup-2.3.1.exe` (the number this branch carried then; the version audit of the same day showed that 2.3.1 is a different, already published release, so the same build is now `Delentia-Setup-2.4.0.exe`), **15.3 MB**. A silent install (`/VERYSILENT`) took **87 seconds** and used 264 MB, created 4 Start-menu entries (Delentia / Stop / Update / Check Delentia installation) and **no start-up entry**. Start-up on custom ports (8123/3123, temporary data folder) took 10 seconds and the Desk page talked to the installed agent. Uninstalling removed the folder, the shortcuts and the registry key, and the real `~/.delentia` listing was identical before and after.
* **Defects the real install found (fixed, with tests):** (1) a dependency published as source only (`robotexclusionrulesparser`) can not be built in the portable Python because pip's isolated build does not work there ("Cannot import setuptools.build_meta"); setuptools and wheel are now installed first and the build uses `--no-build-isolation`; (2) an unwritable pip cache made the install fail, so all three pip steps use `--no-cache-dir`; (3) a silent install whose parts failed used to end with exit code 0 (success). It now ends with a non-zero code (measured with the real compiler: `RaiseException` and `Abort` leave 0, only `ExitProcess` at the very end changes it).
* **Post-install check:** Start -> Delentia -> *Check Delentia installation* (or run `python\python.exe check_install.py` in the install folder). Six checks: the installer's files and log, the version, the Desk inside the package, the libraries, start on free ports then answer and stop, nothing left running. It uses a throw-away data folder, never touches your real data, and writes `check_install_report.txt` that can be sent to whoever helps.
* **Not checked:** a clean machine that never had Python or Node (the builder's machine was used), SmartScreen/antivirus behaviour (the installer is not code-signed and will show a warning), the offline build (`--offline-wheels`), `delentia update --apply` against the real PyPI (waits for the 2.3.1 release), installing over an older version.

## Why Inno Setup + portable Python, not PyInstaller or Tauri
* The system has heavy components and many dynamic imports (the 41-algorithm engine and more). One PyInstaller exe risks silently missing modules and is hard to debug.
* A portable Python plus pip installs the real packages from PyPI: the installer stays small, and updating works with `delentia update --apply`, the same way as for pip users.
* The Tauri desktop app (`apps/gui/src-tauri`) is prepared but its icon is a placeholder and building it needs Rust plus Visual Studio build tools: a separate job, not needed to get people started.
