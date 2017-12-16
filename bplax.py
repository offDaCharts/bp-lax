import cgi
import urllib
import datetime
from operator import itemgetter
import os

from google.appengine.api import users
from google.appengine.ext import ndb

import webapp2
import jinja2

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

DEFAULT_SEASON_NAME = '2018_A'

# We set a parent key on the 'Matches' to ensure that they are all
# in the same entity group. Queries across the single entity group
# will be consistent.  However, the write rate should be limited to
# ~1/second.

def season_key(season_name=DEFAULT_SEASON_NAME):
    """Constructs a Datastore key for a Match entity.

    We use season_name as the key.
    """
    return ndb.Key('Season', season_name)


def player_key():
    """Constructs a global Datastore key for a Player entity."""
    return ndb.Key('Player', 'global_player_root')


class Match(ndb.Model):
    """A main model for representing an individual Match entry."""
    author = ndb.StringProperty(indexed=False)
    winner1 = ndb.StringProperty(indexed=False)
    winner1_cups = ndb.IntegerProperty(indexed=False)
    winner1_bonus = ndb.IntegerProperty(indexed=False)
    winner2 = ndb.StringProperty(indexed=False)
    winner2_cups = ndb.IntegerProperty(indexed=False)
    winner2_bonus = ndb.IntegerProperty(indexed=False)
    winner_total_cups = ndb.IntegerProperty(indexed=False)
    loser1 = ndb.StringProperty(indexed=False)
    loser1_cups = ndb.IntegerProperty(indexed=False)
    loser1_bonus = ndb.IntegerProperty(indexed=False)
    loser2 = ndb.StringProperty(indexed=False)
    loser2_cups = ndb.IntegerProperty(indexed=False)
    loser2_bonus = ndb.IntegerProperty(indexed=False)
    loser_total_cups = ndb.IntegerProperty(indexed=False)
    date = ndb.DateTimeProperty(auto_now_add=True)


class Player(ndb.Model):
    """A model for representing a player."""
    ldap = ndb.StringProperty(indexed=False)
    date = ndb.DateTimeProperty(auto_now_add=True)


class MainPage(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if not user:
            self.redirect(users.create_login_url(self.request.uri))

        template = JINJA_ENVIRONMENT.get_template('index.j2')
        season_name = self.request.get('season_name',
                                          DEFAULT_SEASON_NAME)

        # Calculate list of players for dropdown.
        player_query = Player.query(
            ancestor=player_key()).order(Player.date)
        players = player_query.fetch(1000)

       # Create logout url.
        url = users.create_logout_url(self.request.uri)
        url_linktext = 'Logout'

        # Write the submission form and the footer of the page
        sign_query_params = urllib.urlencode({'season_name':
                                              season_name})
        template_args = {
            'sign_query_params': sign_query_params,
            'season_name': cgi.escape(season_name),
            'sign_query_params': sign_query_params,
            'url': url,
            'url_linktext': url_linktext,
            'players': players,
        }

        # Ancestor Queries, as shown here, are strongly consistent
        # with the High Replication Datastore. Queries that span
        # entity groups are eventually consistent. If we omitted the
        # ancestor from this query there would be a slight chance that
        # Match that had just been written would not show up in a
        # query.
        match_query = Match.query(
            ancestor=season_key(season_name)).order(-Match.date)
        matches = match_query.fetch(100)

        for match in matches:
            # Hotfix for Ali having 2 fucking ldaps :p
#            for key in match:
#                if match[key] == "alfish":
#                    match[key] = "stanfield"
            if match.winner1 == "alfish":
                match.winner1 = "stanfield"
            if match.winner2 == "alfish":
                match.winner2 = "stanfield"
            if match.loser1 == "alfish":
                match.loser1 = "stanfield"
            if match.loser2 == "alfish":
                match.loser2 = "stanfield"
        template_args['matches'] = matches

        # Calculate stats and display.
        user_stats = {}
        for player in players:
            user_stats[player.ldap] = {'wins': 0, 'losses': 0, 'possible_cups': 0, 'made_cups': 0}
        # Run through each game and update the base users stats.
        for match in matches:
            user_stats[match.winner1]['wins'] += 1
            user_stats[match.winner2]['wins'] += 1
            user_stats[match.loser1]['losses'] += 1
            user_stats[match.loser2]['losses'] += 1
            user_stats[match.winner1]['made_cups'] += match.winner1_cups
            user_stats[match.winner1]['possible_cups'] += match.winner_total_cups
            user_stats[match.winner2]['made_cups'] += match.winner2_cups
            user_stats[match.winner2]['possible_cups'] += match.winner_total_cups
            user_stats[match.loser1]['made_cups'] += match.loser1_cups
            user_stats[match.loser1]['possible_cups'] += match.loser_total_cups
            user_stats[match.loser2]['made_cups'] += match.loser2_cups
            user_stats[match.loser2]['possible_cups'] += match.loser_total_cups

        # Run through each player and update calculated user stats.
        sortable_user_list = []
        for k,v in user_stats.iteritems():
            user_stats[k]['games'] = games = v['wins'] + v['losses']
            user_stats[k]['ratio'] = ratio = 0.0 if games == 0 else 1.0 * v['wins'] / games
            user_stats[k]['cpg'] = cpg = 0.0 if games == 0 else 6.0 * v['made_cups'] / v['possible_cups']
            #user_stats[k]['exp'] = exp = min(1.0, games / 10.0)
            exp_threshold = 12.0
            user_stats[k]['exp'] = exp = 1 - 1 / (pow(2 * games / exp_threshold, 3) + pow(games / exp_threshold, 5) + 1)
            #user_stats[k]['bpa'] = bpa = ratio + (2.0 * cpg / 6.0) + exp
            user_stats[k]['bpa'] = bpa = ratio + (3.0 * cpg / 6.0)
            user_stats[k]['ldap'] = k
            sortable_user_list.append(user_stats[k])

        # Sort by BPA.
        sorted_user_stats = sorted(sortable_user_list, key=itemgetter('bpa'), reverse=True)

        template_args['sorted_user_stats'] = sorted_user_stats

        self.response.write(template.render(template_args))

class PostMatch(webapp2.RequestHandler):
    def post(self):
        # We set the same parent key on the 'Match' to ensure each
        # Match is in the same entity group. Queries across the
        # single entity group will be consistent. However, the write
        # rate to a single entity group should be limited to
        # ~1/second.
        season_name = self.request.get('season_name',
                                          DEFAULT_SEASON_NAME)
        match = Match(parent=season_key(season_name))

        if users.get_current_user():
            match.author = users.get_current_user().email()

        match.winner1 = self.request.get('winner1')
        match.winner1_cups = int(self.request.get('winner1_cups')) + int(self.request.get('winner1_bonus'))
        match.winner1_bonus = int(self.request.get('winner1_bonus'))
        match.winner2 = self.request.get('winner2')
        match.winner2_cups = int(self.request.get('winner2_cups')) + int(self.request.get('winner2_bonus'))
        match.winner2_bonus = int(self.request.get('winner2_bonus'))
        match.winner_total_cups = int(self.request.get('winner_total_cups'))
        match.loser1 = self.request.get('loser1')
        match.loser1_cups = int(self.request.get('loser1_cups')) + int(self.request.get('loser1_bonus'))
        match.loser1_bonus = int(self.request.get('loser1_bonus'))
        match.loser2 = self.request.get('loser2')
        match.loser2_cups = int(self.request.get('loser2_cups')) + int(self.request.get('loser2_bonus'))
        match.loser2_bonus = int(self.request.get('loser2_bonus'))
        match.loser_total_cups = int(self.request.get('loser_total_cups'))
        match.put()

        query_params = {'season_name': season_name}
        self.redirect('/?' + urllib.urlencode(query_params))


class PostPlayer(webapp2.RequestHandler):
    def post(self):
        season_name = self.request.get('season_name', DEFAULT_SEASON_NAME)

        player = Player(parent=player_key())
        player.ldap = self.request.get('ldap')
        player.put()

        query_params = {'season_name': season_name}
        self.redirect('/?' + urllib.urlencode(query_params))


app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/postmatch', PostMatch),
    ('/postplayer', PostPlayer),
], debug=True)

