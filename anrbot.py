import praw
import pdb
import re
import json
import sys
from unidecode import unidecode


r=praw.Reddit('anrbot')
s=r.subreddit('anrbot')
#current user: from r.config.username

regex = re.compile(r'\[\[(.*?)\]\]')

def handle_ratelimit(func, *args, **kwargs):
    while True:
        try:
            func(*args, **kwargs)
            break
        except praw.exceptions.APIException as error:
            pdb.set_trace()
            sys.exit(1)

def iterCards(text):
    for cardName in regex.finditer(text):
        yield cardName.group(1)

def normalizeTitle(title):
    return unidecode(title).lower()

def loadCards(fn):
    with open(fn, 'r') as f:
        cards = json.load(f)['data']
        for card in cards:
            card['title_norm'] = normalizeTitle(card['title'])
        return cards

def cardMatches(search, cards):
    for card in cards:
        if search in card['title_norm']:
            yield card

def cardToMarkdown(card):
    (title, code) = (card['title'], card['code'])
    return '%s - [NetrunnerDB](http://netrunnerdb.com/en/card/%s)'%(title, code)

def tagToMarkdown(tag, cards):
    results = [cardToMarkdown(card) 
               for card 
               in cardMatches(normalizeTitle(tag), cards)]

    if not results:
        return "I couldn't find [[%s]]. I'm really sorry. "%(tag,)
    if len(results) > 1:
        rv = "I found several matches for [[%s]]!"%(tag,)
    else:
        rv = ""
    return rv + '\n\n'.join(results)

def parseText(text):
    rv =""
    for tag in iterCards(text):
        rv += tagToMarkdown(tag, cards)
    return rv

def parseComment(comment):
    print "COMMENT", comment.created
    replyText = parseText(comment.body)
    if replyText:
        handle_ratelimit(comment.reply, replyText)

def parseComments(comments, comment_stop, botname):
    for comment in comments: 
        if  comment.created <= comment_stop:
            break
        else:
            if comment.author.name == botname:
                pass
            else:
                parseComment(comment)

def parsePost(post):
    print "POST", post.created
    replyText = parseText(post.selftext)
    if replyText:
        handle_ratelimit(post.reply, replyText)

def parsePosts(submissions, submission_stop, botname):
    for post in submissions:
        if post.created <= submission_stop:
            break
        else:
            if post.author.name == botname:
                pass
            else:
                parsePost(post)

cards = loadCards('cards.json')

# submissions = [post for post in s.submissions()]
# comments = [comment for comment in s.comments(limit=None)]
parsePosts(s.submissions(), 0, 'anrbot')
parseComments(s.comments(), 0, 'anrbot')

