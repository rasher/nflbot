#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
# 
# NFL update bot. 0.2
# 
# Copyright (c) 2009, Jonas Haggqvist
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name of the program nor the names of its contributors may be
#   used to endorse or promote products derived from this software without
#   specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from datetime import date, datetime, timedelta
from pprint import pprint
from twisted.internet import reactor, protocol, task
from twisted.words.protocols import irc
from xml.etree import ElementTree
import feedparser
import locale
import re
import sys
import time
import urllib2

def gamesort(a, b):
    c = cmp(a['start'], b['start'])
    if c == 0:
        return cmp(a['eid'], b['eid'])
    else:
        return c

def getconfig(v):
    c = dict([x.split(':') for x in open('config').readlines()])
    return c[v].strip()

class Team():
    city = ""
    team = ""
    bg = ""
    fg = ""
    stadium = ""
    short = ""

    irccolors = {
        'white':0,
        'black':1,
        'blue':2,
        'green':3,
        'lightred':4,
        'red':5,
        'purple':6,
        'orange':7,
        'yellow':8,
        'lightgreen':9,
        'teal':10,
        'aqua':11,
        'lightblue':12,
        'magenta':13,
        'darkgrey':14,
        'lightgrey':15,
    }

    def __init__(self, city, team, fg, bg, stadium, short):
        self.city = city
        self.team = team
        self.fg = fg
        self.bg = bg
        self.stadium = stadium
        self.short = short

    def shortirc(self):
        return "%c%d,%d%-3s%c" % (
            3,
            self.irccolors[self.fg],
            self.irccolors[self.bg],
            self.short,
            3
        )

class NFLBot(irc.IRCClient):
    nickname = getconfig('nick')
    alreadyrunning = False
    isconnected = False
    games = {}
    bps = []
    playerdetails = {}
    teams = {
        "ARI": Team("Arizona", "Cardinals", "white", "red", "University of Phoenix Stadium", "ARI"),
        "ARZ": Team("Arizona", "Cardinals", "white", "red", "University of Phoenix Stadium", "ARI"),
        "ATL": Team("Atlanta", "Falcons", "black", "red", "Georgia Dome", "ATL"),
        "BAL": Team("Baltimore", "Ravens", "yellow", "lightblue", "M&T Bank Stadium", "BAL"),
        "BUF": Team("Buffalo", "Bills", "red", "blue", "Rogers Centre", "BUF"),
        "CAR": Team("Carolina", "Panthers", "lightblue", "black", "Bank of America Stadium", "CAR"),
        "CHI": Team("Chicago", "Bears", "orange", "lightblue", "Soldier Field", "CHI"),
        "CIN": Team("Cincinnati", "Bengals", "black", "orange", "Paul Brown Stadium", "CIN"),
        "CLE": Team("Cleveland", "Browns", "white", "orange", "Cleveland Browns Stadium", "CLE"),
        "DAL": Team("Dallas", "Cowboys", "blue", "lightgrey", "Cowboys Stadium", "DAL"),
        "DEN": Team("Denver", "Broncos", "orange", "lightblue", "INVESCO Field at Mile High", "DEN"),
        "DET": Team("Detroit", "Lions", "white", "lightblue", "Ford Field", "DET"),
        "GB":  Team("Green Bay", "Packers", "yellow", "green", "Lambeau Field", "GB"),
        "HOU": Team("Houston", "Texans", "red", "blue", "Reliant Stadium", "HOU"),
        "IND": Team("Indianapolis", "Colts", "white", "lightblue", "Lucas Oil Stadium", "IND"),
        "JAC": Team("Jacksonville", "Jaguars", "white", "blue", "Jacksonville Municipal Stadium", "JAC"),
        "KC":  Team("Kansas City", "Chiefs", "white", "red", "Arrowhead Stadium", "KC"),
        "MIA": Team("Miami", "Dolphins", "orange", "teal", "Land Shark Stadium", "MIA"),
        "MIN": Team("Minnesota", "Vikings", "white", "purple", "Hubert H. Humphrey Metrodome", "MIN"),
        "NE":  Team("New England", "Patriots", "blue", "red", "Gillette Stadium", "NE"),
        "NO":  Team("New Orleans", "Saints", "black", "orange", "Louisiana Superdome", "NO"),
        "NYG": Team("New York", "Giants", "blue", "red", "New Meadowlands Stadium", "NYG"),
        "NYJ": Team("New York", "Jets", "white", "green", "New Meadowlands Stadium", "NYJ"),
        "OAK": Team("Oakland", "Raiders", "black", "white", "Oakland-Alameda County Coliseum", "OAK"),
        "PHI": Team("Philadelphia", "Eagles", "black", "teal", "Lincoln Financial Field", "PHI"),
        "PIT": Team("Pittsburgh", "Steelers", "black", "yellow", "Heinz Field", "PIT"),
        "SD":  Team("San Diego", "Chargers", "yellow", "blue", "Qualcomm Stadium", "SD"),
        "SEA": Team("Seattle", "Seahawks", "lightgrey", "blue", "Qwest Field", "SEA"),
        "SF":  Team("San Francisco", "49ers", "red", "orange", "Candlestick Park", "SF"),
        "STL": Team("St. Louis", "Rams", "blue", "orange", "Edward Jones Dome", "STL"),
        "SL":  Team("St. Louis", "Rams", "blue", "orange", "Edward Jones Dome", "STL"),
        "TB":  Team("Tampa Bay", "Buccaneers", "red", "darkgrey", "Raymond James Stadium", "TB"),
        "TEN": Team("Tennessee", "Titans", "aqua", "blue", "LP Field", "TEN"),
        "WAS": Team("Washington", "Redskins", "white", "red", "FedExField", "WAS"),

        "AFC": Team("AFC", "Pro Bowl Team", "white", "red", "", "AFC"),
        "NFC": Team("NFC", "Pro Bowl Team", "blue", "white", "", "NFC"),
    }
    seenurls = []

    def __init__(self):
        self.teamfeeds = []
        self.lastmsg = datetime.now()
        for team in self.teams:
            self.teamfeeds.append((
                self.teams[team],
                "http://www.nfl.com/rss/rsslanding?searchString=team&abbr=%s" % team
             ))
        self.generalfeeds = [
            (None, "http://www.nfl.com/rss/rsslanding?searchString=home"),
            (None, "http://www.nfl.com/rss/rsslanding?searchString=events&id=pro_bowl"),
            (None, "http://www.nfl.com/rss/rsslanding?searchString=events&id=playoffs"),
            (None, "http://www.nfl.com/rss/rsslanding?searchString=events&id=super_bowl"),
            (None, "http://www.nfl.com/rss/rsslanding?searchString=events&id=draft"),
            # Videos
            (None, "http://www.nfl.com/rss/rsslanding?searchString=gamehighlightsVideo"),
            (None, "http://www.nfl.com/rss/rsslanding?searchString=eventVideo&id=super_bowl"),
            (None, "http://www.nfl.com/rss/rsslanding?searchString=eventVideo&id=playoffs"),
            # Twitter
            (None, "http://twitter.com/statuses/user_timeline/40519997.rss"),
        ]
        for team in self.teams:
            if team not in ['AFC', 'NFC', 'SL']:
                self.updateteamplayers(team)


    def gamestring(self, game):
        qs = {
                'F':'Final    ',
                'FO':'Final OT',
                'H':'Halftime ',
                'P':'Pending',
                '1':'1st',
                '2':'2nd',
                '3':'3rd',
                '4':'4th',
                '5':'Overtime ',
        }
        v = {
            'home':self.teams.get(game['h'], Team("", "", "white", "black", "", "TBD")).shortirc(),
            'away':self.teams.get(game['v'], Team("", "", "white", "black", "", "TBD")).shortirc(),
            'c':chr(0x3),
            'vs':int(game['vs']),
            'hs':int(game['hs']),
            'u':'',
            'o':chr(0xf),
            'time':" %s" % qs[game['q']],
            'start':game['start'],
            'start_s':game['start'].strftime("%a %d/%m %H:%M"),
            'stadium':self.teams.get(game['h'], Team("", "", "", "", "Unknown stadium", "")).stadium,
        }

        fixedstadium = {
                '2010013100':'Land Shark Stadium (Pro Bowl)',
                '2010020700':'Land Shark Stadium (Super Bowl)',
        }
        if game['eid'] in fixedstadium:
            v['stadium'] = fixedstadium[game['eid']]

        stadiumadd = {
                '2010012400':' (AFC Final)',
                '2010012401':' (NFC Final)',
        }
        if game['eid'] in stadiumadd:
            v['stadium'] += stadiumadd[game['eid']]

        if game['t'] == 'TBD':
            v['start_s'] = game['start'].strftime("%a %d/%m TBD  ")

        if game['q'] == 'F' or game['q'] == 'FO':
            v['u']=chr(0x1f)
        elif game['q'] in ('1', '2', '3', '4', '5'):
            v['time'] += " %s" % game['k']

        if game['q'] == 'P':
            fmt = "%(away)s @ %(home)s %(start_s)s in %(stadium)s"
        else:
            fmt = "%(away)s %(u)s%(vs)2d @ %(hs)-2d%(o)s %(home)s%(time)s"
        ret = fmt % (v)
        return ret

    def sayall(self, msg):
        for channel in self.factory.channels:
            self.msg(channel, msg)
            self.lastmsg = datetime.now()

    def msg(self, target, msg):
        print "<%s@%s> %s" % (self.nickname, target, msg)
        irc.IRCClient.msg(self, target, msg)

    def saygame(self, game, oldgame):
        if game == None:
            return False
        gamestring = self.gamestring(game)
        if oldgame == None:
            self.sayall(gamestring)
            return True

        scores = {
            1:'Extra point',
            2:'Safety/2pt.',
            3:'Field goal',
            6:'Touchdown!',
        }

        scorech = False
        for score, team in ('hs', 'h'), ('vs', 'v'):
            diff = int(game[score]) - int(oldgame[score])
            if diff != 0:
                scorech = True
                if abs(diff) in scores:
                    scorestr = scores[abs(diff)]
                else:
                    scorestr = "%d points" % abs(diff)
                msg = "%s %s " % (gamestring, self.teams[game[team]].shortirc())
                if diff > 0:
                    msg += "scores %s" % scorestr
                else:
                    msg += "%s is reversed" % scorestr
                self.sayall(msg)

        # Don't print anything else if score changed
        if scorech:
            return True

        if game['rz'] != oldgame['rz'] and game['rz'] != 0 and 'p' in game:
            self.sayall(gamestring + " %s is in the %c%dred zone%c" % (self.teams[game['p']].shortirc(), 3, 5, 3))

        if game['q'] != oldgame['q'] or game['q'] == 'P':
            self.sayall(gamestring)

    def saybp(self, bp):
        self.sayall("%s %s %c%d,%dBIG PLAY ALERT%c: %s" % (
            self.gamestring(self.games[bp['eid']]),
            self.teams[bp['abbr']].shortirc(),
            3,8,5,3,
            bp['x'],
        ))

    def gamestarttime(self, game):
        start = datetime(
                int(game['eid'][0:4]),
                int(game['eid'][4:6]),
                int(game['eid'][6:8]),
                )
        if game['t'] != 'TBD':
            start += timedelta(
                hours=int(game['t'].split(':')[0])+12,
                minutes=int(game['t'].split(':')[1])
            )
        start += timedelta(hours=6)   # Timezone offset
        return start

    def gameloop(self, firstrun=False):
        if not self.isconnected:
            nextupdate = timedelta(minutes=3)
            reactor.callLater(nextupdate.seconds, self.gameloop)
            print("Not connected. Trying again at: %s (in %d seconds)" % (datetime.now() + nextupdate, nextupdate.seconds))
            return False

        print("%-18s - " % "Update gamestatus"),
        url = "http://gaia.local/nfl/"
        url = "http://static.nfl.com/liveupdate/scorestrip/postseason/ss.xml"
        url = "http://www.nfl.com/liveupdate/scorestrip/ss.xml"
        try:
            data = urllib2.urlopen(url)
            tree = ElementTree.parse(data)
        except Exception, e:
            print e
            nextupdate = timedelta(seconds=15)
            print("Next update will be: %s (in %d seconds)" % (datetime.now() + nextupdate, nextupdate.seconds))
            reactor.callLater(nextupdate.seconds, self.gameloop)
            return False


        newgames = [dict(start=self.gamestarttime(g.attrib), **g.attrib) for g in tree.find('gms').findall('g')]
        newgames.sort(gamesort)
        for game in [g.attrib for g in tree.find('gms').findall('g')]:
            game['start'] = self.gamestarttime(game)
            if game != self.games.get(game['eid']) and not firstrun:
                self.saygame(game, self.games.get(game['eid']))
            if game['eid'] not in self.games:
                self.games[game['eid']] = {}
            self.games[game['eid']] = game
        if tree.find('bps'):
            for bp in [b.attrib for b in tree.find('bps').findall('b')]:
                if bp['id'] not in self.bps:
                    self.bps.append(bp['id'])
                    self.saybp(bp)

        # Find out when to update next
        nextupdate = timedelta(minutes=30) # Always update at least every 30 minutes
        for game in self.games:
            game = self.games[game]
            if game['q'] not in ('F', 'P', 'FO'):
                # If there's a running game, we update every 15 seconds
                nextupdate = min(nextupdate, timedelta(seconds=15))
            elif game['q'] == 'P':
                # If there's a pending game, we update every 30 minutes, or
                # the moment the game starts. Or every 5 seconds if the game
                # ought to have started
                start = game['start']
                togo = start - datetime.now() # Calculate how long until start
                if togo < timedelta(): # Game ought to have started, try aggressively
                    nextupdate = min(nextupdate, timedelta(seconds=5))
                else: # Game start is in the future
                    nextupdate = min(nextupdate, togo)
        print("Next update will be: %s (in %d seconds)" % (datetime.now() + nextupdate, nextupdate.seconds))
        reactor.callLater(nextupdate.seconds, self.gameloop)

    def updateteamplayers(self, team):
        url = "http://www.nfl.com/teams/roster?team=%s" % team
        data = urllib2.urlopen(url).read()
        m = re.finditer('<tr class="(?:odd|even)">\s+<td>\s*(?P<number>[0-9]*)\s*</td>\s+<td[^>]*>\s*<a[^>]*>(?P<lastname>[^,]*),\s*(?P<firstname>[^<]*?)\s*</a></td>\s+<td>(?P<pos>[^<]*)</td>\s+<td>(?P<status>[^<]*)</td>\s+<td>\s*(?P<height>[^<]*)\s*</td>\s+<td>\s*(?P<weight>[^<]*)\s*</td>\s+<td>\s*(?P<birthmonth>[0-9]*)/(?P<birthday>[0-9]*)/(?P<birthyear>[0-9]*)\s*</td>\s+<td>\s*(?P<exp>[^<]*)\s*</td>\s+<td>\s*(?P<college>[^<]*)\s*</td>\s*</tr>', data)
        players = []
        self.playerdetails[team] = {}
        for match in m:
            player = self.getplayerdetails(match.groupdict())
            player['team'] = team
            player['team_shortirc'] = self.teams[team].shortirc()
            players.append(player)
        if len(players) > 0:
            self.playerdetails[team]['players'] = players
            self.playerdetails[team]['updated'] = datetime.now()

    def getplayerdetails(self, v):
        v['mheight'] = int(v['height'].split("'")[0])*0.30480 + int(v['height'].split("'")[1][:-1])*0.0254
        v['mweight'] = int(v['weight'])*0.45359237
        v['fullname'] = "%(firstname)s %(lastname)s" % v
        v['wp'] = "http://en.wikipedia.org/wiki/%s" % v['fullname'].replace(' ', '_')
        if v['birthyear'].isdigit() and v['birthmonth'].isdigit() and v['birthday'].isdigit():
            v['bday'] = date(int(v['birthyear']), int(v['birthmonth']), int(v['birthday']))
            v['years'] = (date.today() - v['bday']).days/365
        else:
            v['bday'] = date.fromtimestamp(0)
            v['years'] = -1
        if v['exp'] == '0':
            v['exp_s'] = 'rookie'
        else:
            v['exp_s'] = "%s year veteran" % v['exp']
        return v

    def sayplayer(self, target, v):
        msg = "%(team_shortirc)s #%(number)s %(fullname)s (%(pos)s), %(years)d years, %(status)s, %(height)s (%(mheight).2fm), %(weight)s lbs (%(mweight).fkg), %(exp_s)s, %(college)s - %(wp)s" % v
        self.msg(target, msg)

    def playerquery(self, target=None, team=None, query=None):
        if None in (target, team, query) or team not in self.playerdetails or len(query.strip()) < 3:
            return False
        if datetime.now() - self.playerdetails[team]['updated'] > timedelta(hours=24):
            self.updateteamplayers(team)
        found = False
        for player in self.playerdetails[team]['players']:
            if query.isdigit() and query == player['number']:
                self.sayplayer(target, player)
                return True
            elif query.lower() in player['lastname'].lower() or query.lower() in player['fullname'].lower():
                self.sayplayer(target, player)
                found = True
        if found == True:
            return True
        self.msg(target, "%s %s not found" % (team, query))
        return False

    def rssloop(self, firstrun=False):
        if not self.isconnected:
            nextupdate = timedelta(minutes=3)
            reactor.callLater(nextupdate.seconds, self.rssloop)
            print("Not connected. Trying again at: %s (in %d seconds)" % (datetime.now() + nextupdate, nextupdate.seconds))
            return False

        tosay = {}
        for team, url in self.teamfeeds + self.generalfeeds:
            try:
                feed = feedparser.parse(url)
            except Exception, e:
                print(e)
            else:
                for entry in feed.entries:
                    if entry.link in self.seenurls:
                        continue
                    print "  ***NEW***: %s - %s" % (entry.title, entry.link)
                    self.seenurls.append(entry.link)
                    if firstrun:
                        continue
                    if entry.link not in tosay:
                        tosay[entry.link] = (entry.link, entry.title, datetime(*entry.updated_parsed[0:6]), [])
                    if team != None:
                        tosay[entry.link][3].append(team.shortirc())
        nextupdate = timedelta(minutes=15)
        reactor.callLater(nextupdate.seconds, self.rssloop)
        print("Next update will be: %s (in %d seconds)" % (datetime.now() + nextupdate, nextupdate.seconds))
        tosay = tosay.values()
        tosay.sort(lambda x, y: cmp(x[2], y[2]))
        for link, title, date, teams in tosay:
            start = ""
            if teams != []:
                start = "%s: " % ", ".join(teams)
            msg = "%s%s - %s" % (start, title, link)
            self.sayall(msg.encode('utf-8'))

    def dumprss(self, target=None):
        for url in self.seenurls:
            print(url)

    def saygames(self, target=None):
        games = self.games.values()
        games.sort(gamesort)
        for game in games:
            self.saygame(game, None)

    def signedOn(self):
        """Called when bot has succesfully signed on to server."""
        self.msg("nickserv", "identify %s" % getconfig('password'))
        for channel in self.factory.channels:
            self.join(channel)
        self.isconnected = True
        if not self.alreadyrunning:
            reactor.callLater(10, self.gameloop, firstrun=True)
            reactor.callLater(10, self.rssloop, firstrun=True)
            self.alreadyrunning = True

    def connectionLost(self, reason):
        print "Lost connection: %s" % reason
        self.isconnected = False

    def privmsg(self, user, channel, message):
        nick = user.split("!")[0]
        if channel == self.nickname:
            target = nick
        else:
            target = channel
        print("<%s@%s> %s" % (nick, target, message))

        matchers = [
                (re.compile("^(?P<team>[A-Z]{2,3}) +(?P<query>.*)$"), self.playerquery),
        ]
        for regex, callback in matchers:
            m = regex.search(message)
            if m:
                callback(target=target, **m.groupdict())

    def lineReceived(self, data):
        irc.IRCClient.lineReceived(self, data)


class NFLBotFactory(protocol.ReconnectingClientFactory):
    protocol = NFLBot
    def __init__(self, channels):
        self.channels = channels


if __name__ == "__main__":
    locale.setlocale(locale.LC_ALL, '')
    f = NFLBotFactory(getconfig('channels').split(','))
    reactor.connectTCP(getconfig('server'), 6667, f)
    reactor.run()
