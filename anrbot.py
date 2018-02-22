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
from difflib import get_close_matches

NRDB_SYNCH_INTERVAL=60*60*24
NRDB_ALL_CARDS="https://netrunnerdb.com/api/2.0/public/cards"
RESULTS_LIMIT=10
ABBREVIATIONS_WIKI='abbreviations'
STATUS_WIKI='status'

FOOTER = """

*****
Beep Boop. I am Clanky, the ANRBot. 

[ [About me] ](https://www.reddit.com/r/anrbot/wiki)
[ [Contact] ](https://www.reddit.com/message/compose/?to=just_doug&subject=ANRBot)
"""

class ANRBot(object):
    """Reddit Bot class: respond to names of Android:Netrunner cards
       with helpful information."""

    def __init__(self, 
                 cardsFile='cards.json', 
                 prawConfig='anrbot',
                 sub='anrbot',
                 wikiSub='anrbot'):
        self.r=praw.Reddit(prawConfig)
        self.s=self.r.subreddit(sub)
        self.regex = re.compile(r'\[\[(.*?)\]\]')
        self.botName = self.r.user.me().name
        self.wiki = self.r.subreddit(wikiSub).wiki
        self.abbreviations = self.loadAbbreviations(ABBREVIATIONS_WIKI)
        (self.cards, self.cardDict) = self.loadCards('cards.json')

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
    
    def loadAbbreviations(self, wikiPage=ABBREVIATIONS_WIKI):
        rv={}
        for tag in self.iterTags(self.wiki[wikiPage].content_md):
            fields = tag.split('=')
            if len(fields) == 2:
                rv[self.normalizeTitle(fields[0])] = self.normalizeTitle(fields[1])
        return rv

    def postStatus(self, text, wikiPage=STATUS_WIKI):
        self.wiki[wikiPage].edit(text)

    def normalizeTitle(self, title):
        """Convert a string into the lower-case version of its 
           closest ascii equivalent"""
        rv = ''.join(c for c in unidecode(title).lower() if c.isalnum())
        if rv and rv[-1] == 's':
            rv = rv[:-1]
        return rv


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
            nrdbData = json.load(f)
            imageUrlTemplate = nrdbData['imageUrlTemplate']
            cards = nrdbData['data']
            for card in cards:
                card['title_norm'] = self.normalizeTitle(card['title'])
                card['image_url'] = card.get('image_url', 
                    imageUrlTemplate.replace('{code}', card['code']))
            cardDict = {card['title_norm']:card for card in cards}
            return (cards, cardDict)


    def cardMatches(self, search, cards):
        """Generator yielding all cards with a normalized title
           containing the search term. 
        """
        if search in self.abbreviations:
            search = self.abbreviations[search]
        if search in self.cardDict:
            yield self.cardDict[search]
        else:
            #This is an ugly way to deal with reprints
            # 
            # When you iterate through this, you get cards sorted
            # - in reverse alphabetical order
            # - then by most-recently released first
            matches = reversed(sorted( (card['title'], 
                                        int(card['code'][0:2]), 
                                        card) 
                                       for card in cards 
                                       if search in card['title_norm']))
            last=''
            for (_, _, card) in matches:
                if last == card['title']:
                    continue
                last = card['title']
                yield card


    def cardToMarkdown(self, card):
        """Convert a single card dict into a string containing its
           name and a link to the relevant page in NRDB.
        """
        (title, imageUrl, code) = (card['title'], card['image_url'], card['code'])
        return '[%s](%s) - [NetrunnerDB](https://netrunnerdb.com/en/card/%s)'%(title, imageUrl, code)

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
            # see if we can find any suggestions before giving up.
            # note that the default cutoff for get_close_matches is 0.6
            # documentation for get_close_matches can be found here:
            # https://docs.python.org/2/library/difflib.html#difflib.get_close_matches
            suggestionCutoff = 0.6
            suggestionLimit = 3
            suggestion_strings = get_close_matches(self.normalizeTitle(tag),
                                                   set([card['title'] for card in cards]),
                                                   suggestionLimit,
                                                   suggestionCutoff)
            apologyString = "I couldn't find [[%s]]. I'm really sorry. "%(tag,)
            if len(suggestion_strings) == 0:
                return apologyString
            else:
                retString = apologyString + "Perhaps you meant:\n\n * "
                suggestionResults = []
                for suggestion_str in suggestion_strings:
                    matches = self.cardMatches(self.normalizeTitle(suggestion_str),
                                           cards) 
                    suggestionResults += [self.cardToMarkdown(card)
                                          for card
                                          in matches]
                return retString + '\n\n * '.join(suggestionResults)

        if len(results) == 1:
            return results[0]
        if len(results) > 10:
            return "I found a shitload of matches for [[%s]]!!! Here's the first %d.\n\n * %s"%(tag, 
                  RESULTS_LIMIT, 
                  '\n\n * '.join(results[:RESULTS_LIMIT]))
        else:
            return "I found several matches for [[%s]]!\n\n * %s"%(tag,
                  '\n\n * '.join(results))
   

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
    if len(sys.argv) < 2:
        sys.exit("Usage: %s subreddit"%(sys.argv[0],))
    subreddit = sys.argv[1]
    lastPost = getLast('lastPost')
    lastComment  = getLast('lastComment')

    bot = ANRBot('cards.json', 'anrbot', subreddit)
    print "STARTING %s %f"%(subreddit, time.time())
    lastPost = max(lastPost, bot.parsePosts(lastPost))
    lastComment = max(lastComment, bot.parseComments(lastComment))
    bot.postStatus("**Beep Boop** \r\n\r\nThe last time I ran was %s."%(time.asctime()))
    
    writeLast('lastPost', lastPost)
    writeLast('lastComment', lastComment)
