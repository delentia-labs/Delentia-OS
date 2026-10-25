# Install Delentia on Windows with a double click

The installer is called `Delentia-Setup-<version>.exe` and works like any other program: double-click, press Next until it finishes.

**Status, plainly:** the scripts and files that build the installer are in `installer/windows/`, and everything that can be tested without the compiler has been tested, but **the real `.exe` has not been built yet**. It needs the installer compiler (Inno Setup) and a portable Python, which must be downloaded and are waiting for the owner's permission (see "Building the installer"). So this page has two parts: "For users" (once a file exists) and "For whoever builds it".

## For users

### Install
1. Double-click `Delentia-Setup-<version>.exe`. No administrator rights; it installs for your account only.
2. Windows may show "Windows protected your PC" (SmartScreen) because the file is not code-signed yet. Press **More info → Run anyway** if you downloaded it from the official release page and its SHA-256 matches the one announced.
3. Press Next. You may choose a desktop icon.
4. The installer copies files, then downloads and installs the parts Delentia needs. **It needs the internet and takes 3-10 minutes.** If it fails, a window says why and where the log (`install.log`) is; connect and run the installer again.
5. Tick "Open Delentia now" on the last page.

### Use
Start menu → **Delentia** has three entries (green icon with eyes):
* **Delentia** starts the program (no black window) and opens it in your browser at `http://localhost:3010`. The first start takes 20-60 seconds.
* **Stop Delentia** stops what Delentia started (and only that).
* **Update Delentia** checks for and installs a newer version (always asks first). See `UPDATES_EN.md`.

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
* **Not checked:** compiling with the real Inno Setup, installing on a clean machine, SmartScreen/antivirus behaviour, real installer size and time.

## Why Inno Setup + portable Python, not PyInstaller or Tauri
* The system has heavy components and many dynamic imports (the 41-algorithm engine and more). One PyInstaller exe risks silently missing modules and is hard to debug.
* A portable Python plus pip installs the real packages from PyPI: the installer stays small, and updating works with `delentia update --apply`, the same way as for pip users.
* The Tauri desktop app (`apps/gui/src-tauri`) is prepared but its icon is a placeholder and building it needs Rust plus Visual Studio build tools: a separate job, not needed to get people started.
