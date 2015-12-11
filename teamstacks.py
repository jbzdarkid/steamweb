from __future__ import print_function
from re import search, match, finditer, DOTALL, MULTILINE
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

def get_concurrent_players(swb):
    r = swb.get('http://steamcommunity.com/my/friends/players')
    if match('http://steamcommunity.com/id/[^/]+/friends/$', r.url):
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
    return players, playerNames

if __name__ == "__main__":
    swb = SteamWebBrowserCfg()
    if not swb.logged_in():
        swb.login()
    players, playerNames = get_concurrent_players(swb)

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

    if len(groups) == len(players):
        print('No groups in this game.')
    else:
        print('Groups in this game:')
        for group in groups:
            if len(group) == 1:
                continue
            out = 'Group of size '+str(len(group))+': '
            for player in group:
                out += '"'+HTMLParser().unescape(playerNames[player]).decode('utf-8')+'", '
            print(out[:-2])
