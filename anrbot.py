#!/usr/bin/env python
import praw
import pdb
import re
import json
import sys
from unidecode import unidecode
import urllib
import os
import time

NRDB_SYNCH_INTERVAL=60*60*24
NRDB_ALL_CARDS="https://netrunnerdb.com/api/2.0/public/cards"

FOOTER = """

*****
I am Clanky, the ANRBot. [Source](https://github.com/carlsondc/anrbot)
"""

class ANRBot(object):
    """Reddit Bot class: respond to names of Android:Netrunner cards
       with helpful information."""

    def __init__(self, 
                 cardsFile='cards.json', 
                 prawConfig='anrbot',
                 sub='anrbot'):
        self.cards = self.loadCards('cards.json')
        self.r=praw.Reddit(prawConfig)
        self.s=self.r.subreddit(sub)
        self.regex = re.compile(r'\[\[(.*?)\]\]')
        self.botName = self.r.user.me().name


    def rateLimitedReply(self, replyFunc, *args, **kwargs):
        """Repeatedly attempt calls to Comment.reply or
           Submission.reply until it completes. 
           
           Return server timestamp of reply."""
        while True:
            try:
                lastComment = replyFunc(*args, **kwargs)
                return lastComment.created
            except praw.exceptions.APIException as error:
                print >> sys.stderr, "Rate-limited"
                time.sleep(30)
                print >> sys.stderr, "Retrying"


    def iterTags(self, text):
        for tag in self.regex.finditer(text):
            yield tag.group(1)


    def normalizeTitle(self, title):
        """Convert a string into the lower-case version of its 
           closest ascii equivalent"""
        return unidecode(title).lower()


    def loadCards(self, fn):
        """Load the cards database at fn into its unpacked form. Add
           the normalized title to each card's dict.
           
           If fn is missing or its modified time exceeds
           NRDB_SYNCH_INTERVAL, fetch a fresh copy from NRDB."""
        if os.path.isfile(fn):
            elapsed = time.time() - os.stat(fn).st_mtime
        else:
            elapsed = NRDB_SYNCH_INTERVAL
        if elapsed >= NRDB_SYNCH_INTERVAL:
            print "Refreshing cards"
            uo = urllib.URLopener()
            uo.retrieve(NRDB_ALL_CARDS,
                fn)
        with open(fn, 'r') as f:
            cards = json.load(f)['data']
            for card in cards:
                card['title_norm'] = self.normalizeTitle(card['title'])
            return cards


    def cardMatches(self, search, cards):
        """Generator yielding all cards with a normalized title
           containing the search term. 
        """
        for card in cards:
            if search in card['title_norm']:
                yield card


    def cardToMarkdown(self, card):
        """Convert a single card dict into a string containing its
           name and a link to the relevant page in NRDB.
        """
        (title, code) = (card['title'], card['code'])
        return '[%s](https://netrunnerdb.com/card_image/%s.png) - [NetrunnerDB](https://netrunnerdb.com/en/card/%s)'%(title, code, code)


    def tagToMarkdown(self, tag, cards):
        """Convert a single tag from a comment/post into a string
           reply. This will either be an apology (if the tag 
           matches no cards), or a string containing the names/links
           to all of the matched cards for that tag.
        """
        results = [self.cardToMarkdown(card) 
                   for card 
                   in self.cardMatches(self.normalizeTitle(tag), 
                                       cards)]
    
        if not results:
            return "I couldn't find [[%s]]. I'm really sorry. "%(tag,)
        if len(results) > 1:
            return "I found several matches for [[%s]]!\n\n * %s"%(tag,
                  '\n\n * '.join(results))
        else:
            return results[0]
   

    def parseText(self, text):
        """Concatenate the results of all tags found within text.
        """
        results = []
        for tag in self.iterTags(text):
            results.append(self.tagToMarkdown(tag, 
                                              self.cards))
        return '\n\n'.join(results)
    

    def parseComment(self, comment):
        """Check comment text for tags and reply if any are found."""
        replyText = self.parseText(comment.body)
        if replyText:
            print "COMMENT REPLY", comment.created
            self.rateLimitedReply(comment.reply,
                replyText+FOOTER)
            return comment.created
        else:
            print "COMMENT IGNORE", comment.created
            return comment.created
    

    def parseComments(self, stopTime):
        """Check all comments from the current time until stopTime for
           tags and reply to each of them.

           Return the server timestamp of the last reply made, or None
           if no replies were made."""
        lastReply = None
        print "COMMENTS START", stopTime
        for comment in self.s.comments():
            if  comment.created <= stopTime:
                print "COMMENTS END", comment.created, stopTime, "last", lastReply
                return lastReply
            else:
                if comment.author.name == self.botName:
                    # better safe than sorry
                    pass
                else:
                    lastReply = max(lastReply,
                        self.parseComment(comment))
        print "COMMENTS END (no comments left)", stopTime, "last", lastReply
        return lastReply
   

    def parsePost(self, post):
        """Check submission text for tags and reply if any are found."""
        replyText = self.parseText(post.selftext)
        if replyText:
            print "POST REPLY", post.created
            self.rateLimitedReply(post.reply, replyText + FOOTER)
            return post.created
        else:
            print "POST IGNORE", post.created
            return post.created

   

    def parsePosts(self, stopTime):
        """Check all submissions from the current time until stopTime
           for tags and reply to each of them.
           
           Return the server timestamp of the last reply made, or None
           if no replies were made."""
        lastReply = None
        print "POSTS START", stopTime
        for post in self.s.submissions():
            if post.created <= stopTime:
                # print "POST SKIP", post.created, stopTime
                print "POSTS END", post.created, stopTime, "last", lastReply
                return lastReply
            else:
                if post.author.name == self.botName:
                    # better safe than sorry
                    pass
                else:
                    lastReply = max(lastReply, self.parsePost(post))
        print "POSTS END (no posts left)", stopTime, "last", lastReply
        return lastReply

def getLast(fn):
    if os.path.isfile(fn):
        with open(fn, 'r') as f:
            return float(f.readline().strip())
    else:
        print >>sys.stderr, "file missing:", fn
        sys.exit(1)

def writeLast(fn, timestamp):
    with open(fn, 'w') as f:
        f.write(str(timestamp))

if __name__ == '__main__':
    lastPost = getLast('lastPost')
    lastComment  = getLast('lastComment')

    bot = ANRBot('cards.json', 'anrbot', 'netrunner')
    print "STARTING", time.time()
    lastPost = max(lastPost, bot.parsePosts(lastPost))
    lastComment = max(lastComment, bot.parseComments(lastComment))
    
    writeLast('lastPost', lastPost)
    writeLast('lastComment', lastComment)
