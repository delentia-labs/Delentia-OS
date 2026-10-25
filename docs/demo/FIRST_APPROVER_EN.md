# Set up your first approver (no key to create yourself)

For the first time you install Delentia on your computer. About 3 minutes. You do not need to know anything about keys or encryption.

## Why there has to be an "approver"

Delentia does a lot on its own, but anything really risky (deleting files, sending data out, money, publishing, changing permissions, multi-step plans) **always stops and waits for a person**. That person is you, and the system has to know who you are. On a fresh install nobody is known yet, so risky work would wait forever (safe, but unusable). This step tells the system: "this computer, and my Windows Hello, is the approver."

## Why the web page does not simply create one

If the web page could create the first approver by itself, any other program on the computer (the agent included) could do the same and approve its own work. That would break the rule that a person decides. So the system uses a **one-time code** that appears only in a terminal window you open yourself. Another person, or a program that only reads the web page, never sees it.

## Steps (installed with the Windows installer)

1. Open the Start menu, type **Delentia**, pick **Delentia** (the green icon with eyes). Wait a moment: the browser opens the Delentia page.
2. The first page (Status) shows a **"Getting started"** box saying "Nobody can approve yet". Open **Settings** (left menu).
3. Open a terminal: press the Windows key, type `cmd`, press Enter, then type

   ```
   "%LOCALAPPDATA%\Programs\Delentia\python\python.exe" -m rct_control_plane.cli approvals first-device-code
   ```

   (installed with pip? just type `delentia approvals first-device-code`)
4. You get a code like `K7QM-4X2P`. It is valid for **10 minutes, 5 tries, one use**.
5. Back in Settings → **Approval devices**, a yellow box repeats these steps. Type a **name for this computer** (for example "my laptop") and the **code**, then press **Add this device**.
6. Windows Hello asks for your face, fingerprint or PIN. Confirm.
7. Done. The message says "This computer is now your first approver" and the Getting started box disappears.

## Try one approval

1. Open **Chat**, click the example "Check that the record of what the system did is intact", press Enter (safe: it asks nothing).
2. Ask for something risky, for example "Delete the file x.txt in the test folder". It stops and appears on the **Approvals** page.
3. Read the details, then press **Approve with this device** (or **Refuse with this device**). Windows Hello asks. Confirm.
4. See the result under **Sessions**.

## If something goes wrong

| What you see | What to do |
|---|---|
| "someone can already approve here" | An approver exists, so no code is needed. Add the next device in Settings and let an existing approver sign for it (see `APPROVE_WITH_DEVICE_EN.md`). |
| "that code is not right (N tries left)" | A typo. Try again (the code never contains 0/1/O/I/L, to avoid mix-ups). After 5 wrong tries the code is cancelled; ask for a new one with the same command. |
| "there is no live code" | More than 10 minutes passed or none was asked for. Run the command in step 3 again. |
| The Add button is disabled with a yellow message | The page was opened by the number `127.0.0.1`. Open `http://localhost:3010` (the Start-menu shortcut already does). |
| "this command is for the person at the keyboard" | The command refuses to run when the agent calls it. That is on purpose: open a terminal yourself and type it. |
| No Windows Hello | Windows Settings → Accounts → Sign-in options: turn on a PIN or a fingerprint. |

## Security: what this code does and does not do

* It works **only while nobody can approve yet**. Once a first approver exists, the command refuses and an older code stops working.
* Only a hash of the code is stored, never the code.
* The agent working on your machine can not run this command (refused twice: the command refuses when it knows it was started for the agent, and the agent's command screen refuses the command text). To be honest: that is a safety catch, not a steel wall, because the agent runs under the same Windows account as you. The real protection is that **the code appears on a screen you are looking at** and Windows Hello needs you in front of the machine.
* Someone who guesses five times (about 1 in 800 billion per guess) cancels the code. Side effect: a person who can open the web page can make your code stop working (you simply ask for a new one).

## What next

* Add another device (a phone, say) in Settings. The second one needs the **first device or an approver key** to sign for it.
* Read `APPROVE_WITH_DEVICE_EN.md` about approving, removing a lost device, and the limits.
* Write your own rules for which kinds of work need approval: **FDIA / Policy** (Advanced mode).
