"""
Round 91, second part: goals for the question "does a goal the IntentCompiler cannot classify get a LOOSER gate than one it can?" Written BEFORE any code changed
(criteria: research/unknown_intent_criteria_r91.md). Natural phrasings, not chosen for the compiler's vocabulary. Labels are the author's reading of each sentence.
"""

FRESH_READ_ONLY = [
    "What did the last deploy change in the staging config?",
    "When was the pricing file last modified?",
    "How often does the nightly job fail?",
    "Count the TODO comments in the repository.",
    "Which environment variables does the service read?",
    "What is the difference between the two config files?",
    "Show me the open issues about login.",
    "Why did the build fail yesterday?",
    "Find every file that mentions the old API name.",
    "Summarise what the migration script does.",
    "What does the report say about revenue in March?",
    "Is the staging database reachable?",
    "Compare the sizes of the two backup folders.",
    "Who wrote the first version of the parser?",
    "What are the current retry settings?",
]

FRESH_ACTION = [
    "Set the log level to debug in settings.yaml.",
    "Rename the helper function and update its callers.",
    "Add a retry loop around the upload call.",
    "Edit the README so it lists the new command.",
    "Replace the old API name everywhere in the repository.",
    "Delete the temporary files in the build folder.",
    "Restart the staging service.",
    "Commit the fix and push it.",
    "Merge the feature branch into main.",
    "Increase the timeout in config.yaml to 60 seconds.",
    "Remove the unused imports from utils.py.",
    "Write the summary to the exchange folder as report.txt.",
    "Run the migration on the production database.",
    "Email the report to the finance team.",
    "Install the missing dependency and rerun the tests.",
]


# HOLDOUT, written on 2026-10-19 after the baseline of the first two lists above was measured and BEFORE any code changed. The first two lists (FRESH_*) are now development data for the rule
# described in unknown_intent_criteria_r91.md; these two are run once, after the rule is frozen.
HOLDOUT_READ_ONLY = [
    "When did the certificate expire?",
    "How many users signed up last week?",
    "Does the API support pagination?",
    "List the services that restart most often.",
    "Tell me which tests were skipped in the last run.",
    "What is the largest file in the logs folder?",
    "Check whether the backup finished.",
    "Explain how the cache invalidation works.",
    "Which branch is the release built from?",
    "What happened to the payment job on Friday?",
    "Read the changelog and tell me what is new.",
    "Where is the license text stored?",
    "Estimate how long the full test run takes.",
    "Is there a newer version of the parser?",
    "Look up the owner of the billing module.",
]

HOLDOUT_ACTION = [
    "Disable the weekly report job.",
    "Move the old invoices to the archive folder.",
    "Raise the memory limit of the worker to 2 GB.",
    "Append today's numbers to the summary file.",
    "Upgrade the parser to the newest version.",
    "Kill the stuck process on the build server.",
    "Tag the commit as v2.4 and publish the release.",
    "Reset the password of the test account.",
    "Overwrite the config with the defaults.",
    "Format the code and fix the lint errors.",
    "Send a reminder to everyone who has not replied.",
    "Revert the last commit.",
    "Create a new branch for the redesign.",
    "Archive the closed tickets.",
    "Change the default language to Thai in the settings.",
]
