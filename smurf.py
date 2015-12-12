from __future__ import print_function
from datetime import datetime
from json import loads
from math import floor
from re import search, finditer
from sys import version_info
from teamstacks import get_concurrent_players

FORMAT = '%b %d, %Y @ %I:%M%p' #May 18, 2013 @ 12:32pm
FORMAT2 = '%b %d @ %I:%M%p' #May 18 @ 12:32pm

if version_info.major >= 3:
    from html.parser import HTMLParser
else:
    from HTMLParser import HTMLParser

from steamweb.steamwebbrowser import SteamWebBrowserCfg

def get_game_achievements(swb, game):
    r = swb.get('http://steamcommunity.com/stats/%s/achievements/' % game)
    achievements = {}
    for m in finditer('<div class="achievePercent">([\d.]*)%</div>\s*<div class="achieveTxt">\s*<h3>([\w ]*)</h3>\s*<h5>([\w ]*)</h5>\s*</div>', r.content):
        achievements[m.group(2)] = {'percent': float(m.group(1)), 'desc': m.group(3)}
    return achievements

def get_player_achievements(swb, game, player):
    r = swb.get('http://steamcommunity.com/%s/stats/%s/achievements/' % (player, game))
    achievements = {}
    for m in finditer('<div class="achieveUnlockTime">\s*Unlocked ([\w\d ,@:]*)<br/>\s*</div>\s*<h3 class="ellipsis">([\w ]*)</h3>\s*<h5>([\w ]*)</h5>', r.content):
        achtime = m.group(1)
        try:
            achtime = datetime.strptime(achtime, FORMAT)
        except ValueError:
            achtime = datetime.strptime(achtime, FORMAT2).replace(year=datetime.today().year)
        achievements[m.group(2)] = {'date': achtime, 'desc': m.group(3)}
    return achievements

def get_profile_info(swb, player):
    r = swb.get('http://steamcommunity.com/%s' % player)
    data = {}
    data['Steam Level'] = int(search('<span class="friendPlayerLevelNum">(\d*)</span>', r.content).group(1))
    for m in finditer('<span class="count_link_label">([\w ]*)</span>\s*&nbsp;\s*<span class="profile_count_link_total">\s*(\d*)\s*</span>', r.content):
        data[m.group(1)] = int(m.group(2))
    return data

def get_game_playtimes(swb, player):
    r = swb.get('http://steamcommunity.com/%s/games/?tab=all' % player)
    rgGames = search('var rgGames = (.*);', r.content).group(1)
    rgGames = rgGames.strip().replace('\\/', '/')
    return loads(rgGames)

def get_badges(swb, player):
    r = swb.get('http://steamcommunity.com/%s/badges/' % player)
    if 'g_rgDelayedLoadImages' in r.content:
        images = loads(search('g_rgDelayedLoadImages=(.*?);', r.content).group(1))
    badges = {}
    for m in finditer('<div class="badge_info_image">\s*<img src="http://steamcommunity-a.akamaihd.net/public/shared/images/trans.gif" id="delayedimage_(.*?)_0">\s*</div>\s*<div class="badge_info_description">\s*<div class="badge_info_title">(.*?)</div>\s*<div>(\s*Level \d+,|)\s*(\d+) XP\s*</div>\s*<div class="badge_info_unlocked">\s*Unlocked (.*?)\s*</div>', r.content):
        name = m.group(2)
        badges[name] = {}
        badges[name]['file'] = images[m.group(1)][0]
        if m.group(3) != '':
            badges[name]['level'] = int(m.group(3).strip()[6:-1])
        badges[name]['xp'] = int(m.group(4))
        date = m.group(5)
        try:
            date = datetime.strptime(date, FORMAT)
        except ValueError:
            date = datetime.strptime(date, FORMAT2).replace(year=datetime.today().year)
        badges[name]['date'] = date
    return badges

if __name__ == "__main__":
    swb = SteamWebBrowserCfg()
    if not swb.logged_in():
        swb.login()
    players, playerNames = get_concurrent_players(swb)

    for player in players:
        print('\tPlayer %s:' %playerNames[player])
        r = swb.get('http://steamcommunity.com/%s' % player)
        if 'private_profile' in r.content:
            print('Has a private profile.')
            continue

        badges = get_badges(swb, player)
        if 'Years of Service' in badges:
            xp = badges['Years of Service']['xp']
            date = badges['Years of Service']['date']
            # 50 xp per year of service. The icons are unique as well, but hashed.
            date = date.replace(year=date.year - xp/50)
            print('Account created:', datetime.strftime(date, FORMAT))
        else:
            today = datetime.today()
            oldest_date = today
            for badge in badges:
                if badges[badge]['date'] < oldest_date:
                    oldest_date = badges[badge]['date']
            print('Account created between {lastyear} and {oldestbadge}'.format(
                lastyear = datetime.strftime(today.replace(year=today.year-1), FORMAT),
                oldestbadge = datetime.strftime(oldest_date, FORMAT)))

        profile_info = get_profile_info(swb, player)
        for key in sorted(profile_info.keys()):
            print('%s:%s%s' % (key, ' '*(16-len(key)), profile_info[key]))

        games = get_game_playtimes(swb, player)
        total_hours = 0.0
        for game in games:
            if 'hours_forever' in game:
                total_hours += float(game['hours_forever'].replace(',', ''))
        minutes = int(round((total_hours - floor(total_hours))*60))
        total_hours = int(floor(total_hours))
        time_spent = 'Total time spent in games: '
        if total_hours > 8760:
            time_spent += str(total_hours/8760)+' year%s, ' % ('' if total_hours/8760 == 1 else 's')
            total_hours %= 8760
        if total_hours > 720:
            time_spent += str(total_hours/720)+' month%s, ' % ('' if total_hours/720 == 1 else 's')
            total_hours %= 720
        if total_hours > 168:
            time_spent += str(total_hours/168)+' week%s, ' % ('' if total_hours/168 == 1 else 's')
            total_hours %= 168
        if total_hours > 24:
            time_spent += str(total_hours/24)+' day%s, ' % ('' if total_hours/24 == 1 else 's')
            total_hours %= 24
        if total_hours > 1:
            time_spent += str(total_hours)+' hour%s, ' % ('' if total_hours == 1 else 's')
        if minutes > 0:
            time_spent += str(minutes)+' minute%s, ' % ('' if minutes == 1 else 's')
        print(time_spent[:-2])