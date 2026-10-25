# Approve risky work with your own device (Windows Hello) instead of typing a command

Written for people who do not write code. Do it once per computer; after that you approve by pressing a button and confirming your face, fingerprint or PIN.

## What changed, and what did not

* **Changed:** instead of opening a terminal and typing `delentia approvals approve ...` every time, you press **"Approve with this device"** on the Approvals page and Windows Hello asks who you are. One press approves and runs that action once.
* **Not changed:** safe work needs no approval at all (there is no "approve everything" button and no plain click-approve). Approval is for really risky work only: delete, send out, money, publish, multi-step plans. Every approval is recorded in the verifiable record: who approved, with which device, when, and it runs only once.
* The private key of Windows Hello **never leaves the device**. The system keeps only the public key.

## Before you start (check 3 things)

1. Windows Hello is set up: Windows Settings → Accounts → Sign-in options → at least one method (face, fingerprint or PIN).
2. There is **an approver**. On a fresh install there is none yet: do `FIRST_APPROVER_EN.md` first (a one-time code from a terminal, no key to create). If you already have an approver key, skip that. The reason the **next** device needs an existing approver to sign for it: nobody who merely reaches the web page may add their own device as an approver.
3. **Open the Desk at `localhost`, not the number `127.0.0.1`.** The browser refuses Windows Hello on a page opened by a number. The Start-menu shortcut and `delentia desk` already open it correctly; if you type it, use `http://localhost:3010`.

## Add this device (once)

1. Desk → **Settings** → **Approval devices**.
2. Type a name (for example "my laptop") and press **Add this device**. Windows Hello asks. Confirm.
3. The device shows **"waiting for an approver"** (it can not approve yet; that is the intended gate).
4. Have an existing approver sign for it: `delentia approvals review --key <your approver key>` (or double-click `SIGN_PENDING.bat`). It lists what waits in plain words; you should see the line *"this lets a device named 'my laptop' approve actions from now on"*. If you added it yourself, press `a`. If you did not add it, press `r`. Unsure: `s` (skip).
5. Back in Settings press **Activate**. The device is **active**.

(The very first device is different: with the one-time code from `FIRST_APPROVER_EN.md` it is active at once.)

## Approve work

1. Open **Approvals**. Read the details completely (a multi-step plan is shown as steps 1, 2, 3 with the kind of each).
2. Press **Approve with this device**. Windows Hello asks. Confirm.
3. The system approves and runs it at once; a message confirms. See the result under **Sessions**.
4. Disagree? Press **Refuse with this device**. The action will not run.

Work that needs two signatures: one device gives one signature. Another device (or another approver key) must sign too.

## Remove a device (lost, no longer used)

Settings → **Remove** next to the device name. It can approve nothing any more, and anything it approved that has not run yet becomes void (it must be asked for again). Removing is always allowed and needs no signature.

## If something is wrong

| What you see | Usual cause | What to do |
|---|---|---|
| The Add button is disabled with a yellow message | Opened by `127.0.0.1`, or the browser has no WebAuthn | Open `http://localhost:3010` |
| "Cancelled or timed out" | You cancelled, or waited over 2 minutes | Nothing was recorded; try again |
| "This device is already registered" | This device was added before | Look at the list in Settings |
| No "Approve with this device" button | No **active** device yet | Finish "Add this device" until it says active |
| "Not allowed" after pressing | The action needs a role or scope this device does not have | Use an approver key, or a device that has it |

## Limits (said plainly)

* Your device signs the action's **digest** (a fingerprint of what will be done), not the text you see on screen. So the screen must be trustworthy: open it at `localhost` on your own machine, read before you press, and for the riskiest work require two signers.
* If the computer is left unlocked, whoever sits at it can press the button (Windows Hello still asks who they are).
* If your Microsoft account syncs passkeys to other devices, their safety equals that account's. The system records whether a passkey can be synced (`backup_eligible`).
* The author tested with a WebAuthn software authenticator in a real browser (the data formats follow the standard and ES256 and RS256 signatures are verified for real), but **not yet with your real Windows Hello**. If something looks odd, say exactly what you saw.
