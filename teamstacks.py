#!/usr/bin/env python
from __future__ import print_function
from re import search, finditer, DOTALL, MULTILINE
from copy import copy
from sys import version_info
if version_info.major >= 3:
    from html.parser import HTMLParser
else:
    from HTMLParser import HTMLParser

from steamweb.steamwebbrowser import SteamWebBrowserCfg

def get_friends(swb, id):
    r = swb.get('http://steamcommunity.com/{id}/friends'.format(id=id))
    return [friend.group(1) for friend in finditer('<a class="friendBlockLinkOverlay" href="http://steamcommunity.com/(.*?)"></a>', r.content)]

swb = SteamWebBrowserCfg()
if not swb.logged_in():
    swb.login()

r = swb.get('http://steamcommunity.com/my/friends/players')
if re.match('http://steamcommunity.com/id/[^/]+/friends/$', r.url):
    raise Exception('Not in game.')

players = []
playerNames = {}
for player in finditer('<a class="friendBlockLinkOverlay" href="http://steamcommunity.com/(.*?)".*?<div>(.*?)<br />', r.content, MULTILINE | DOTALL):
    players.append(player.group(1))
    playerNames[player.group(1)] = player.group(2).strip()
# The player who called the program
player = search('<a href="http://steamcommunity.com/(.*?)" data-miniprofile="\d*">(.*?)</a>', r.content)
players.append(player.group(1))
playerNames[player.group(1)] = player.group(2)

groups = []
for player in players:
    group = set([player])
    for friend in get_friends(swb, player):
        if friend in players:
            group.add(friend)
    groups.append(group)

i = 0
while i < len(groups):
    for player in copy(groups[i]):
        j = 0
        while j < i:
            if player in groups[j]:
                groups[i].update(groups[j])
                del groups[j]
                i -= 1
            j += 1
    i += 1

for group in sorted(groups, key=lambda s: -len(s)):
    names = []
    for player in group:
        names.append(HTMLParser().unescape(playerNames[player]))
    print(names)