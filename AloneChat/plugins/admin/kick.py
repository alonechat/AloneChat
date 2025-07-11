from core.plugin import Plugin
from core.network.protocol import Message, MessageType

class KickPlugin(Plugin):
    def initialize(self, context):
        self.server = context.get('server')

    def execute(self, sender, target):
        if sender == "admin":
            msg = Message(MessageType.KICK, sender, "", target)
            asyncio.create_task(self.server.process_message(msg))
            return True
        return False

class PluginImpl(KickPlugin):
    pass