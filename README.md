ANRBot
------
A helpful little dude that looks up Android: Netrunner cards on
NetrunnerDB.com and provides links to them.

- code clean up / bug fixes: 
  - parseComment/parseReply can be consolidated if you
    pass in the relevant string (comment.body vs. submission.selftext)
  - not re-entrant, so cron has to schedule it conservatively to
    prevent double-posts. should be fine to just create/check a dumb
    lockfile from the bash script (write PID to file, detect dead
    instance with pgrep)
  - in the event that the bot gets interrupted after it starts posting
    comments but before it can finish and update the timestamp files,
    restarting it will cause it to duplicate posts. Would be nice to
    check the children of the comment/submission being processed to
    make sure we haven't already responded to it.
