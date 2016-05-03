import json, re, threading, time, urllib2, websocket
from exceptions import SlackError

SLACK_API_BASE = 'https://slack.com/api/'

class SlackBot(object):
    """
    The SlackBot class represents a Bot Integration connection to a Slack team.
    
    """
    def __init__(self, api_token, debug=False):
        self.api_token = api_token
        self.event_listeners = {}
        self.message_id = 0
        self.show_typing = False
        self.debug = debug
        self._threads = []

    def add_event_listener(self, event, handler):
        """
        Add a listener function which runs when ``event`` occurs.

        Arguments:
            event   -- One of: open, close, error, message, presence_change, user_typing
            handler -- Function to execute when the event occurs.
        
        """
        if event not in self.event_listeners:
            self.event_listeners[event] = []

        self.event_listeners[event].append(handler)

    def add_thread(self, f):
        self._threads.append(f)
        
    def channel_from_id(self, id):
        """Return SlackChannel object with given id."""
        for channel in self.channels:
            if channel.id == id:
                return channel
        else:
            raise SlackError('No channel with id %s' % id)
        
    def get_channel_id(self, channel_name):
        """Convert channel name to channel id."""
        for channel in self.channels:
            if channel.name == channel_name:
                return channel.id
        else:
            raise SlackError('Unknown channel: %s' % channel_name)

    def get_user_id(self, user_name):
        """Convert username to user id."""
        for user in self.users:
            if user.username == user_name:
                return user.id
        else:
            raise SlackError('Unknown user: %s' % user_name)

    def match_message(self, pattern):
        """
        Create event handler that runs when a message matching ``pattern`` is observed.

        Example::
            @bot = SlackBot('<api token>')
            @bot.match_message('!insult <name>')
            def insult(msg, name):
                bot.say(msg.channel, '%s is a damn fool!' % name)
        
        """
        re_pattern = '^' + re.sub('<([^>]+)>', r'(?P<\1>.*?)', pattern)
        if re_pattern.find('(?P') != -1:
            re_pattern += '$'
            
        def inner_decorator(f):
            def message_handler(msg):
                m = re.match(re_pattern, msg.text, re.I)
                if m:
                    f(msg, **m.groupdict())
            self.add_event_listener('message', message_handler)
        return inner_decorator

    def match_regex(self, regex):
        """
        Create event handler that runs when a message matching ``regex`` is observed.

        Example::
            @bot = SlackBot('<api token>')
            @bot.match_regex('^!insult (.*)$')
            def insult(msg, match):
                bot.say(msg.channel, '%s is a damn fool!' % match.group(0))
        
        """
        def inner_decorator(f):
            def message_handler(msg):
                m = re.match(regex, msg.text)
                if m:
                    f(msg, m)
            self.add_event_listener('message', message_handler)
        return inner_decorator

    def on_interval(self, interval):
        """Create event handler that runs periodically (every ``interval`` seconds)"""
        def inner_decorator(f):
            def interval_function():
                while True:
                    time.sleep(interval)
                    if self.running:
                        f()
                    else:
                        return
            self.add_thread(interval_function)
        return inner_decorator
    
    def on_close(self, f):
        """Add event handler to run when websocket connection is closed."""
        self.add_event_listener('close', f)

    def on_error(self, f):
        """Add event handler to run when websocket error occurs."""
        self.add_event_listener('error', f)

    def on_message(self, f):
        """Add event handler to run when a chat message occurs."""
        self.add_event_listener('message', f)

    def on_open(self, f):
        """Add event handler to run when websocket connection is created."""
        self.add_event_listener('open', f)

    def on_presence_change(self, f):
        """Add event handler to run when a user enters or leaves."""
        self.add_event_listener('presence_change', f)

    def on_timeout(self, interval):
        """Create event handler that runs after ``interval`` seconds."""
        def inner_decorator(f):
            def timeout_function():
                time.sleep(interval)
                if self.running:
                    f()
                else:
                    return
            self.add_thread(timeout_function)
        return inner_decorator
    
    def on_user_typing(self, f):
        """Add event handler to run when a user is typing."""
        self.add_event_listener('user_typing', f)

    @staticmethod
    def rtm_call(endpoint, **args):
        """Make Slack API call via RTM protocol."""
        params = ''
        for key in args:
            if params: params += '&'
            params += key + '=' + args[key]
        url = SLACK_API_BASE + endpoint + '?' + params
        result = json.loads(urllib2.urlopen(url).read())
        return result

    def run(self):
        t = self.thread()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.ws.close()
            return
        
    def say(self, channel_id, text):
        """Send chat message from bot."""
        if self.show_typing:
            for i in range(0, 2):
                msg = json.dumps({'id': self._next_message_id(),
                                  'type': 'typing',
                                  'channel': channel_id})
                self.ws.send(msg)
                time.sleep(1)
                
        msg = json.dumps({'id': self._next_message_id(),
                          'type': 'message',
                          'channel': channel_id,
                          'text': text})
        self.ws.send(msg)

    def stop(self):
        self.ws.close()
        self.running = False

    def thread(self, **kwargs):
        self._thread = threading.Thread(target=self._run, **kwargs)
        self._thread.daemon = True
        self._thread.start()
        return self._thread

    def user_from_id(self, id):
        """Return SlackUser object with given id."""
        for user in self.users:
            if user.id == id:
                return user
        else:
            raise SlackError('No user with id %s' % id)

    def _fire_event(self, event, *args, **kwargs):
        if event in self.event_listeners:
            for handler in self.event_listeners[event]:
                handler(*args, **kwargs)

    def _next_message_id(self):
        self.message_id += 1
        return self.message_id

    def _print_debug(self, *args):
        if self.debug:
            print ' '.join(args)
    def _run(self):
        """Run bot synchronously in the foreground."""
        def on_open(ws):
            self._fire_event('open')

        def on_message(ws, message):
            self._print_debug(message)
            e = SlackEvent.from_dict(json.loads(message))
            self._fire_event(e.type, e)
                    
        def on_error(ws, error):
            self._fire_event('error', error)
            
        def on_close(ws):
            self._fire_event('close')

        start_result = SlackBot.rtm_call('rtm.start', token=self.api_token)
        if start_result['ok']:
            self.user_id = start_result['self']['id']
            self.user_username = start_result['self']['name']
            self.user_prefs = start_result['self']['prefs']
            self.users = []
            for user in start_result['users']:
                self.users.append(SlackUser.from_dict(user))

            self.channels = []
            for channel in start_result['channels']:
                self.channels.append(SlackChannel.from_dict(channel))   


            self.ws = websocket.WebSocketApp(start_result['url'],
                                             on_message = on_message,
                                             on_error = on_error,
                                             on_close = on_close,
                                             on_open = on_open)

            websocket.enableTrace(self.debug)

            self.running = True
            for fn in self._threads:
                threading.Thread(target=fn).start()
            
            self.ws.run_forever()
            self.running = False
        else:
            raise SlackError('Could not initiate RTM session')

class SlackChannel:
    """Basic representation of a Slack chat channel"""

    @staticmethod
    def from_dict(d):
        """Create a SlackChannel object from a dictionary of attributes."""
        c = SlackChannel()
        c.id = d['id']
        c.is_archived = d['is_archived']
        c.is_general = d['is_general']
        if d.has_key('members'):
            c.members = d['members']
        c.name = d['name']
        if d.has_key('topic') and d['topic'].has_key('value'):
            c.topic = d['topic']['value']
        return c

class SlackUser:
    """Basic representation of a Slack user"""

    @staticmethod
    def from_dict(d):
        """Create a SlackUser object from a dictionary of attributes."""
        u = SlackUser()
        u.id = d['id']
        u.username = d['name']
        u.presence = d['presence']
        if d.has_key('profile'):
            if d['profile'].has_key('email'):
                u.email = d['profile']['email']
            if d['profile'].has_key('first_name'):
                u.first_name = d['profile']['first_name']
            if d['profile'].has_key('last_name'):
                u.last_name = d['profile']['last_name']
            if d['profile'].has_key('real_name'):
                u.real_name = d['profile']['real_name']
        return u
    
class SlackEvent:
    """Basic representation of a Slack event object"""

    @staticmethod
    def from_dict(d):
        """Create a SlackEvent object from a dictionary of attributes."""
        e = SlackEvent()
        e.type = d['type']

        if d['type'] == 'message':
            e.ts = float(d['ts'])
            e.user = d['user']
            e.channel = d['channel']
            e.text = d['text']
        elif d['type'] == 'presence_change':
            e.user = d['user']
            e.presence = d['presence']
        return e
