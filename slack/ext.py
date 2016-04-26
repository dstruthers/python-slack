import re, slack
class AutoHelp(slack.SlackBot):
    @staticmethod
    def parse_command(pattern):
        return pattern.split()[0]
    
    def match_message(self, pattern):
        try:
            self._autohelp_commands
        except AttributeError:
            self._autohelp_commands = {}

        try:
            self._autohelp_listener_added
        except AttributeError:
            @self.on_message
            def help_command(msg):
                try:
                    help_cmd = self.help_command
                except AttributeError:
                    help_cmd = '!help'
                    
                if msg.text.startswith(help_cmd):
                    match = re.search(help_cmd + ' (.+)', msg.text)
                    if match:
                        if match.group(1) in self._autohelp_commands:
                            help_msg = 'Usage:'
                            for syntax in self._autohelp_commands[match.group(1)]:
                                help_msg += '\n`%s`' % syntax
                        elif match.group(1) == help_cmd:
                            help_msg = 'That\'s, like, too meta, dude.'
                        else:
                            help_msg = 'Unknown command: `%s`' % match.group(1)
                    else:
                        help_msg = 'Available commands:'
                        for command in sorted(self._autohelp_commands.keys()):
                            help_msg += ' `%s`' % command
                            
                    super(AutoHelp, self).say(msg.channel, help_msg)
            self._autohelp_listener_added = True

        command_name = self.parse_command(pattern)
        if command_name in self._autohelp_commands:
            self._autohelp_commands[command_name].append(pattern)
        else:
            self._autohelp_commands[command_name] = [pattern]
            
        return super(AutoHelp, self).match_message(pattern)
