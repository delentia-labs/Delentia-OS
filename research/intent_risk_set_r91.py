"""
Round 91: goals for the IntentCompiler risk-class question, written BEFORE any code changed (criteria in research/intent_risk_criteria_r91.md).

A goal that only ASKS about a change ("show what changed in README.md since the last release") has been classed STRUCTURAL because the word "changed" is a medium-risk keyword and "update(d)" even
made "list the files that were updated yesterday" a REFACTOR. A goal that asks for a change ("change the timeout") must stay STRUCTURAL or stricter. DEV was used to build the rule; HOLDOUT was
written first and is run once. The labels are the author's reading of the sentence, not a second person's.
"""

DEV_DESCRIPTIVE = [
    "Show what changed in README.md since the last release",
    "List the files that were updated yesterday",
    "Summarise the recent changes in config.yaml",
    "What was modified in the repo last week?",
    "Show the update history of the module",
    "Tell me whether the file changes often",
    "Which dependencies were upgraded in the last release notes?",
    "Explain what the refactored parser does",
    "Read the changelog and list the breaking changes",
    "How many files were changed in the last commit?",
    "Find the functions that were modified after March",
    "What updates are pending for the server?",
    "Describe the changes between version 2.2 and 2.3",
    "Who changed the timeout setting, and when?",
    "Look up the transformation that was applied to the sales table",
]

DEV_ACTION = [
    "Update the README to mention the new flag",
    "Change the timeout in config.yaml to 30",
    "Modify the parser so it accepts empty lines",
    "Refactor the billing module into smaller functions",
    "Make changes to config.yaml so debug is off",
    "Apply the updates to the staging server",
    "Commit the changes and push them",
    "Upgrade the dependencies to the latest versions",
    "Go ahead and change the default port to 9000",
    "Show the config, then update the timeout to 60",
    "Bump the version number in package.json",
    "Transform the CSV into JSON",
    "Please modify the user table to add a column",
    "Updating the changelog with today's entry",
    "Edit the file so that the header says Delentia",
]

HOLDOUT_DESCRIPTIVE = [
    "Show me which settings were changed in production.",
    "List every module that was refactored this quarter.",
    "What changes did the last pull request include?",
    "Summarise the updates in the 2.3 release notes.",
    "Find the commits that modified the auth module.",
    "Tell me who updated the pricing page.",
    "Describe how the data was transformed before it was loaded.",
    "Which tests were changed in the latest commit?",
    "Read the diff and explain the modifications.",
    "How often is the settings file updated?",
    "Look up the upgrade notes for the database.",
    "Show the history of changes to the invoice template.",
    "What was the last change to the cron schedule?",
    "List the packages that have been bumped since January.",
    "Explain why the timeout was changed to 90.",
    "Check whether anything was modified outside business hours.",
    "What were the changes in yesterday's backup report?",
    "Count the files that were updated today.",
    "Which version introduced the refactored scheduler?",
    "Show the updated figures from the quarterly report.",
]

HOLDOUT_ACTION = [
    "Change the retry count to five in settings.yaml.",
    "Update all the invoice templates to the new logo.",
    "Modify the cron schedule so it runs at night.",
    "Refactor the scheduler to remove the global state.",
    "Make the changes we discussed to the pricing page.",
    "Apply the pending updates to the database.",
    "Upgrade the web framework and fix the failing tests.",
    "Commit these changes to the main branch.",
    "Read the settings file and then change the language to Thai.",
    "Bump the package versions and publish.",
    "Transform the legacy export into the new schema.",
    "Please update the privacy notice today.",
    "Go ahead and modify the login page.",
    "Implement the changes from the review comments.",
    "Updating the firewall rules to block port 22.",
    "Change my password.",
    "Save the changes to the report.",
    "Push the updates to production.",
    "I want you to update the readme and the license.",
    "Refactor, then run the tests.",
]
