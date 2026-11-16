# Thai tool menu, Amendment 1 (2026-11-16, written before the holdout form was filled and before any holdout run)

Its own file because the criteria file is not edited after it is committed.

## What happened since the criteria
1. Rule T1 was built (`rct_control_plane/tool_menu.py`: `THAI_NOUNS`, `THAI_VERBS`, `thai_expansion`, switch `DELENTIA_TOOL_MENU_THAI`, default off) and tuned looking at the 119 development sentences and the first negative set (`tool_menu_thai_negatives_r115.json`).
2. The first run of the plain table (verbs and nouns alike) gave 68% on the development sentences but pulled 1.45 external tools into the menu of the Thai requests that need none (rule 3 needs at most 1). The cause, read from the sentences: a verb such as 'read' or 'delete' matches every external tool that has that verb in its name, even when the request is about a file or a web page. The table was changed so that verbs count only when a domain NOUN (note, ticket, calendar, mail, folder) is present in the request, and 'ข้อความ' no longer counts as a mail noun after 'เป็น' or 'ภาษา'; 'จด' was added as a note noun (not 'จดหมาย', 'จดทะเบียน'). Development result after the change: 67.2% of the development sentences have every needed tool in the menu (literal wording 100%, synonym 71.7%, indirect 24.1%), the mean menu grows by 2.05 tools, and the first negative set pulls 0.1 external tools per request.
3. The table is now FROZEN at the commit that carries this file. It is not changed after the holdout is run.

## Changes to the criteria
* **Guard (c) is now the SECOND negative set** (`tool_menu_thai_negatives2_r115.json`, 20 requests, written after the first set was used for tuning and before it was run). The first set is development data now. Rule 3 is unchanged (at most 1 external tool per request on average).
* The development number (67.2%) is below the 70% bar of rule 1 and says nothing about adoption: only the holdout decides. If the holdout is below 70% or below +40 points, T1 is not proposed, whatever the development number was.

## What the table cannot do (stated before the holdout)
A request with no domain noun ('4412 ตอนนี้เป็นไงแล้ว', 'ส่งเรื่อง 12 ต่อให้มะลิ', 'สัปดาห์หน้าฉันมีอะไรบ้าง') names no server, so T1 adds nothing for it; that is the reason the indirect wording scores low. Closing that gap needs meaning, not a word table (an embedding model that reads Thai: more accurate, slower, needs Ollama), which is a separate candidate with its own criteria.
